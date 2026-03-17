#!/usr/bin/env python3
"""
Example UDP client for Raspberry Pi Camera Streaming Server

This client demonstrates how to connect to the UDP streaming server
and receive video frames over the internet using the NAT-friendly protocol.
"""

import socket
import struct
import pickle
import cv2
import time
import threading
import sys

class UDPVideoClient:
    def __init__(self, server_ip, server_port=9999):
        self.server_ip = server_ip
        self.server_port = server_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = False
        
        # Frame reassembly state
        self.pending_frames = {}  # frame_id -> bytearray
        self.expected_chunks = {}  # frame_id -> remaining chunk count
        
        # Statistics
        self.frames_received = 0
        self.last_frame_time = time.time()
        self.fps = 0.0
        
    def connect(self):
        """Register with the server"""
        print(f"Connecting to {self.server_ip}:{self.server_port}...")
        self.socket.sendto(b"REGISTER_CLIENT", (self.server_ip, self.server_port))
        
        # Wait for registration acknowledgment
        self.socket.settimeout(5.0)
        try:
            data, addr = self.socket.recvfrom(1024)
            if data == b"REGISTERED":
                print("✅ Successfully registered with server!")
                self.socket.settimeout(None)  # Remove timeout
                return True
            else:
                print(f"❌ Unexpected response: {data}")
                return False
        except socket.timeout:
            print("❌ Registration timeout - server not responding")
            return False
    
    def send_keepalive(self):
        """Send periodic keepalive messages"""
        while self.running:
            try:
                self.socket.sendto(b"KEEPALIVE", (self.server_ip, self.server_port))
                time.sleep(15)  # Send every 15 seconds
            except:
                break
    
    def start_streaming(self):
        """Start receiving and displaying video frames"""
        if not self.connect():
            return False
        
        self.running = True
        
        # Start keepalive thread
        keepalive_thread = threading.Thread(target=self.send_keepalive)
        keepalive_thread.daemon = True
        keepalive_thread.start()
        
        print("🎥 Starting video stream... Press ESC to exit")
        
        try:
            while self.running:
                data, addr = self.socket.recvfrom(65507)
                
                if data.startswith(b"FRAME_START"):
                    self._handle_frame_start(data)
                elif data.startswith(b"CHUNK"):
                    self._handle_chunk(data)
                    
        except KeyboardInterrupt:
            print("\n🛑 Interrupted by user")
        except Exception as e:
            print(f"❌ Error receiving data: {e}")
        finally:
            self.stop()
        
        return True
    
    def _handle_frame_start(self, data):
        """Handle FRAME_START packet"""
        if len(data) < 23:  # 11 + 4 + 4 + 4
            return
        
        frame_id, frame_size, chunk_count = struct.unpack("LLL", data[11:23])
        
        # Initialize frame buffer
        self.pending_frames[frame_id] = bytearray(frame_size)
        self.expected_chunks[frame_id] = chunk_count
        
        # Clean up old incomplete frames (keep only last 5)
        if len(self.pending_frames) > 5:
            oldest_frame = min(self.pending_frames.keys())
            self.pending_frames.pop(oldest_frame, None)
            self.expected_chunks.pop(oldest_frame, None)
    
    def _handle_chunk(self, data):
        """Handle CHUNK packet"""
        if len(data) < 13:  # 5 + 4 + 4
            return
        
        frame_id, chunk_index = struct.unpack("LL", data[5:13])
        payload = data[13:]
        
        if frame_id not in self.pending_frames:
            return  # Frame start not received or already processed
        
        # Place chunk in frame buffer
        offset = chunk_index * 1200  # Default chunk payload size
        frame_buffer = self.pending_frames[frame_id]
        
        if offset + len(payload) <= len(frame_buffer):
            frame_buffer[offset:offset + len(payload)] = payload
            self.expected_chunks[frame_id] -= 1
            
            # Check if frame is complete
            if self.expected_chunks[frame_id] == 0:
                self._process_complete_frame(frame_id, bytes(frame_buffer))
    
    def _process_complete_frame(self, frame_id, frame_data):
        """Process a complete frame"""
        # Remove from pending
        self.pending_frames.pop(frame_id, None)
        self.expected_chunks.pop(frame_id, None)
        
        try:
            # Deserialize and decode frame
            jpeg_buffer = pickle.loads(frame_data)
            frame = cv2.imdecode(jpeg_buffer, cv2.IMREAD_COLOR)
            
            if frame is not None:
                # Update statistics
                self.frames_received += 1
                current_time = time.time()
                if current_time - self.last_frame_time >= 1.0:
                    self.fps = self.frames_received / (current_time - self.last_frame_time + 1.0)
                    self.last_frame_time = current_time
                    self.frames_received = 0
                
                # Add FPS overlay
                cv2.putText(frame, f"FPS: {self.fps:.1f}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"Frame ID: {frame_id}", (10, 70), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                
                # Display frame
                cv2.imshow('Raspberry Pi Camera Stream', frame)
                
                # Check for exit key
                if cv2.waitKey(1) & 0xFF == 27:  # ESC key
                    self.running = False
                    
        except Exception as e:
            print(f"⚠️  Error processing frame {frame_id}: {e}")
    
    def stop(self):
        """Stop the client"""
        self.running = False
        try:
            self.socket.sendto(b"DISCONNECT", (self.server_ip, self.server_port))
        except:
            pass
        self.socket.close()
        cv2.destroyAllWindows()
        print("👋 Client stopped")

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 client_example.py <server_ip>")
        print("Example: python3 client_example.py 192.168.1.100")
        sys.exit(1)
    
    server_ip = sys.argv[1]
    
    print("🎬 Raspberry Pi Camera UDP Client")
    print(f"📡 Server: {server_ip}:9999")
    print("🔧 Protocol: Always-chunked UDP with frame IDs")
    print()
    
    client = UDPVideoClient(server_ip)
    
    try:
        success = client.start_streaming()
        if not success:
            print("❌ Failed to start streaming")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Client error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
