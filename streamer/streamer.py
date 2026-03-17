#!/usr/bin/env python3
"""
Video capture and network streaming for Raspberry Pi 5
Supports multiple streaming methods: UDP, TCP, HTTP streaming
"""

import cv2
import logging
import os
import socket
import struct
import pickle
import threading
import time
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
import io
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer
from config import parse_stream_config

LOGGER = logging.getLogger("streamer")


def configure_logging(log_path: str = "logs/streamer.log") -> None:
    if LOGGER.handlers:
        return
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    handler = logging.FileHandler(log_path)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)

class VideoStreamer:
    def __init__(
        self,
        resolution=(640, 480),
        framerate=30,
        bitrate=2_000_000,
        gop=30,
        profile="baseline",
    ):
        # Initialize camera
        self.picam2 = Picamera2()
        config = self.picam2.create_video_configuration(
            main={"size": resolution, "format": "RGB888"}
        )
        self.picam2.configure(config)
        self.picam2.start()

        # Configure H.264 encoder (for future H.264-based pipelines)
        self.h264_encoder = H264Encoder(
            bitrate=bitrate,
            profile=profile,
            intra_period=gop,
        )
        LOGGER.info(
            "Encoder config: bitrate=%s gop=%s profile=%s",
            bitrate,
            gop,
            profile,
        )
        
        self.resolution = resolution
        self.framerate = framerate
        self.bitrate = bitrate
        self.gop = gop
        self.profile = profile
        self.running = False
        
    def capture_frame(self):
        """Capture a single frame from camera"""
        frame = self.picam2.capture_array()
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

class UDPVideoStreamer(VideoStreamer):
    """Stream video over UDP (fast but no reliability guarantee)"""
    
    def __init__(self, host='0.0.0.0', port=9999, **kwargs):
        super().__init__(**kwargs)
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.max_packet_size = 65507  # Max UDP packet size
        self.clients = {}  # Dictionary to store client addresses and last seen time
        self.client_timeout = 30  # Timeout in seconds for inactive clients
        self.frames_sent = 0  # Counter for total frames sent
        self.last_status_time = time.time()  # Time of last status message
        self.status_interval = 10  # Status update every 10 seconds
        self.fixed_client_port = 9999  # Use same port for frames as registration
        self.chunk_payload_size = 1200  # Bytes per UDP chunk payload to avoid IP fragmentation
        self.next_frame_id = 0  # Monotonically increasing frame identifier (uint32 wraparound)
        
    def start_streaming(self):
        """Start UDP video server - wait for clients and then stream"""
        self.running = True
        print(f"Starting UDP video server on {self.host}:{self.port}")
        print("Frames will be sent back to exact client source address (NAT-friendly)")
        print("Waiting for client connections...")
        
        # Start client listener thread
        listener_thread = threading.Thread(target=self.listen_for_clients)
        listener_thread.daemon = True
        listener_thread.start()
        
        # Start streaming thread (will only stream when clients are connected)
        streaming_thread = threading.Thread(target=self.stream_to_clients)
        streaming_thread.daemon = True
        streaming_thread.start()
        
        # Start client cleanup thread
        cleanup_thread = threading.Thread(target=self.cleanup_inactive_clients)
        cleanup_thread.daemon = True
        cleanup_thread.start()
        
        # Keep main thread alive
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def listen_for_clients(self):
        """Listen for client registration messages"""
        while self.running:
            try:
                self.socket.settimeout(1.0)  # Non-blocking with timeout
                data, addr = self.socket.recvfrom(1024)
                
                # Check for client registration message
                if data.startswith(b"REGISTER_CLIENT"):
                    # Use exact source address for frame transmissions (NAT-friendly)
                    client_addr = addr  # Use source IP:port as-is for NAT traversal
                    
                    self.clients[client_addr] = time.time()
                    print(f"Client registered: {client_addr} - frames will be sent to this exact address")
                    # Send acknowledgment
                    self.socket.sendto(b"REGISTERED", addr)
                elif data == b"KEEPALIVE":
                    # Find client by source IP (regardless of port)
                    client_addr = None
                    for registered_addr in self.clients.keys():
                        if registered_addr[0] == addr[0]:  # Same IP
                            client_addr = registered_addr
                            break
                    if client_addr:
                        self.clients[client_addr] = time.time()
                elif data == b"DISCONNECT":
                    # Find client by source IP (regardless of port)
                    client_addr = None
                    for registered_addr in list(self.clients.keys()):
                        if registered_addr[0] == addr[0]:  # Same IP
                            client_addr = registered_addr
                            break
                    if client_addr:
                        del self.clients[client_addr]
                        print(f"Client disconnected: {client_addr}")
                        
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Client listener error: {e}")
                break
    
    def stream_to_clients(self):
        """Stream video frames to registered clients"""
        while self.running:
            try:
                if not self.clients:
                    # No clients connected, wait
                    time.sleep(0.1)
                    continue
                
                frame = self.capture_frame()
                
                # Encode frame as JPEG
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                data = pickle.dumps(buffer)
                
                # Prepare frame id and send to all registered clients
                frame_id = self.next_frame_id
                disconnected_clients = []
                for client_addr in list(self.clients.keys()):
                    try:
                        self.send_frame_to_client(data, client_addr, frame_id)
                    except Exception as e:
                        print(f"Error sending to client {client_addr}: {e}")
                        disconnected_clients.append(client_addr)
                
                # Remove clients that failed to receive
                for client_addr in disconnected_clients:
                    if client_addr in self.clients:
                        del self.clients[client_addr]
                        print(f"Removed unresponsive client: {client_addr}")
                
                # Increment frame counter and show periodic status
                self.next_frame_id = (self.next_frame_id + 1) & 0xFFFFFFFF
                self.frames_sent += 1
                current_time = time.time()
                if current_time - self.last_status_time >= self.status_interval:
                    client_count = len(self.clients)
                    fps = self.frames_sent / (current_time - (self.last_status_time - self.status_interval))
                    print(f"Status: {self.frames_sent} frames sent to {client_count} client(s) | FPS: {fps:.1f}")
                    self.last_status_time = current_time
                    
                time.sleep(1/self.framerate)
                
            except Exception as e:
                print(f"UDP streaming error: {e}")
                break
    
    def send_frame_to_client(self, data, client_addr, frame_id):
        """Send a frame to a specific client using small UDP chunks to avoid fragmentation.

        Protocol:
        - FRAME_START + [frame_id:uint32][frame_size:uint32][chunk_count:uint32]
        - CHUNK + [frame_id:uint32][chunk_index:uint32] + chunk_payload (<= chunk_payload_size)
        """
        size = len(data)
        payload_size = self.chunk_payload_size
        if payload_size <= 0:
            payload_size = 1200

        # Compute chunk count
        chunk_count = (size + payload_size - 1) // payload_size

        # Send frame start header
        frame_header = struct.pack("LLL", frame_id, size, chunk_count)
        self.socket.sendto(b"FRAME_START" + frame_header, client_addr)

        # Send chunk packets
        chunk_index = 0
        for offset in range(0, size, payload_size):
            chunk = data[offset:offset + payload_size]
            chunk_header = struct.pack("LL", frame_id, chunk_index)
            self.socket.sendto(b"CHUNK" + chunk_header + chunk, client_addr)
            chunk_index += 1
    
    def cleanup_inactive_clients(self):
        """Remove clients that haven't sent keepalive messages"""
        while self.running:
            try:
                current_time = time.time()
                inactive_clients = []
                
                for client_addr, last_seen in self.clients.items():
                    if current_time - last_seen > self.client_timeout:
                        inactive_clients.append(client_addr)
                
                for client_addr in inactive_clients:
                    del self.clients[client_addr]
                    print(f"Removed inactive client: {client_addr}")
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                if self.running:
                    print(f"Client cleanup error: {e}")
                break
                
    def stop(self):
        self.running = False
        self.socket.close()
        self.picam2.stop()

class TCPVideoStreamer(VideoStreamer):
    """Stream video over TCP (reliable but slower)"""
    
    def __init__(self, host='0.0.0.0', port=8888, **kwargs):
        super().__init__(**kwargs)
        self.host = host
        self.port = port
        self.clients = []
        
    def start_server(self):
        """Start TCP server for video streaming"""
        self.running = True
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(5)
        
        print(f"TCP video server started on {self.host}:{self.port}")
        
        # Start frame capture thread
        capture_thread = threading.Thread(target=self.capture_and_broadcast)
        capture_thread.daemon = True
        capture_thread.start()
        
        # Accept client connections
        while self.running:
            try:
                client_socket, addr = server_socket.accept()
                print(f"Client connected: {addr}")
                self.clients.append(client_socket)
                
                # Handle client in separate thread
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket,))
                client_thread.daemon = True
                client_thread.start()
                
            except Exception as e:
                print(f"Server error: {e}")
                break
                
        server_socket.close()
        
    def capture_and_broadcast(self):
        """Capture frames and broadcast to all clients"""
        while self.running:
            try:
                frame = self.capture_frame()
                
                # Encode frame
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                data = pickle.dumps(buffer)
                
                # Send to all connected clients
                disconnected_clients = []
                for client in self.clients:
                    try:
                        # Send frame size first
                        size = struct.pack('L', len(data))
                        client.sendall(size)
                        # Send frame data
                        client.sendall(data)
                    except:
                        disconnected_clients.append(client)
                
                # Remove disconnected clients
                for client in disconnected_clients:
                    self.clients.remove(client)
                    client.close()
                    
                time.sleep(1/self.framerate)
                
            except Exception as e:
                print(f"Capture error: {e}")
                break
                
    def handle_client(self, client_socket):
        """Handle individual client connection"""
        try:
            while self.running:
                time.sleep(0.1)  # Keep connection alive
        except:
            pass
        finally:
            if client_socket in self.clients:
                self.clients.remove(client_socket)
            client_socket.close()
            
    def stop(self):
        self.running = False
        for client in self.clients:
            client.close()
        self.picam2.stop()

class HTTPVideoStreamer(VideoStreamer):
    """Stream video over HTTP (MJPEG streaming)"""
    
    def __init__(self, host='0.0.0.0', port=8080, **kwargs):
        super().__init__(**kwargs)
        self.host = host
        self.port = port
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        
    class StreamingHandler(BaseHTTPRequestHandler):
        def __init__(self, streamer_instance):
            self.streamer = streamer_instance
            
        def __call__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            
        def do_GET(self):
            if self.path == '/stream.mjpg':
                self.send_response(200)
                self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=--jpgboundary')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Pragma', 'no-cache')
                self.end_headers()
                
                while True:
                    try:
                        with self.server.streamer.frame_lock:
                            if self.server.streamer.latest_frame is not None:
                                frame = self.server.streamer.latest_frame.copy()
                            else:
                                continue
                                
                        # Encode frame as JPEG
                        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        
                        # Send MJPEG frame
                        self.wfile.write(b'--jpgboundary\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', str(len(buffer)))
                        self.end_headers()
                        self.wfile.write(buffer.tobytes())
                        self.wfile.write(b'\r\n')
                        
                        time.sleep(1/self.server.streamer.framerate)
                        
                    except Exception as e:
                        print(f"HTTP streaming error: {e}")
                        break
                        
            else:
                # Serve simple HTML page
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                html = f'''
                <html>
                <head><title>Raspberry Pi Video Stream</title></head>
                <body>
                <h1>Raspberry Pi Video Stream</h1>
                <img src="/stream.mjpg" width="{self.server.streamer.resolution[0]}" height="{self.server.streamer.resolution[1]}">
                </body>
                </html>
                '''
                self.wfile.write(html.encode())
                
    def start_server(self):
        """Start HTTP server for MJPEG streaming"""
        self.running = True
        
        # Create custom handler with streamer reference
        handler = lambda *args, **kwargs: self.StreamingHandler(self)(*args, **kwargs)
        
        httpd = HTTPServer((self.host, self.port), handler)
        httpd.streamer = self  # Add reference to streamer
        
        print(f"HTTP video server started on http://{self.host}:{self.port}")
        print(f"View stream at: http://{self.host}:{self.port}/stream.mjpg")
        
        # Start frame capture thread
        capture_thread = threading.Thread(target=self.capture_frames)
        capture_thread.daemon = True
        capture_thread.start()
        
        # Start HTTP server
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.shutdown()
            
    def capture_frames(self):
        """Continuously capture frames"""
        while self.running:
            try:
                frame = self.capture_frame()
                with self.frame_lock:
                    self.latest_frame = frame
                time.sleep(1/self.framerate)
            except Exception as e:
                print(f"Frame capture error: {e}")
                break
                
    def stop(self):
        self.running = False
        self.picam2.stop()

# Example usage
if __name__ == "__main__":
    configure_logging()
    config = parse_stream_config()

    print("Choose streaming method:")
    print("1. UDP Streaming (fast, unreliable)")
    print("2. TCP Streaming (reliable, slower)")
    print("3. HTTP/MJPEG Streaming (web browser compatible)")
    
    choice = input("Enter choice (1-3): ").strip()
    
    try:
        if choice == "1":
            streamer = UDPVideoStreamer(
                host='0.0.0.0',
                port=9999,
                resolution=config.resolution,
                framerate=config.fps,
                bitrate=config.bitrate,
                gop=config.gop,
                profile=config.profile,
            )
            streamer.start_streaming()
        elif choice == "2":
            streamer = TCPVideoStreamer(
                host='0.0.0.0',
                port=8888,
                resolution=config.resolution,
                framerate=config.fps,
                bitrate=config.bitrate,
                gop=config.gop,
                profile=config.profile,
            )
            streamer.start_server()
        elif choice == "3":
            streamer = HTTPVideoStreamer(
                host='0.0.0.0',
                port=8080,
                resolution=config.resolution,
                framerate=config.fps,
                bitrate=config.bitrate,
                gop=config.gop,
                profile=config.profile,
            )
            streamer.start_server()
        else:
            print("Invalid choice")
            
    except KeyboardInterrupt:
        print("\nStopping stream...")
        if 'streamer' in locals():
            streamer.stop()
    except Exception as e:
        print(f"Error: {e}")