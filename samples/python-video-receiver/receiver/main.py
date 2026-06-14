#!/usr/bin/env python3
"""
UDP Video Client - receives UDP video streams
"""

import argparse
import cv2
import json
from pathlib import Path
import socket
import struct
import pickle
import sys
import time
import threading
from typing import Any, Dict
import zlib

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config" / "config.json"

DEFAULT_SETTINGS = {
    "mode": None,
    "stream_format": "jpeg",
    "server_ip": None,
    "server_port": 9999,
    "client_port": 9999,
    "listen_port": 9999,
}

VALID_MODES = {"client_server", "broadcast"}
VALID_STREAM_FORMATS = {"jpeg", "h264"}


def _validate_port(name: str, value: int) -> None:
    if not isinstance(value, int) or not (1 <= value <= 65535):
        raise ValueError(
            f"Invalid {name}: {value}. Expected an integer in 1..65535."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="UDP Video Receiver")
    parser.add_argument(
        "--config",
        help=(
            "Path to JSON config file. Defaults to "
            f"{DEFAULT_CONFIG_PATH} when present."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        help="Receiver mode to use",
    )
    parser.add_argument(
        "--stream-format",
        choices=sorted(VALID_STREAM_FORMATS),
        help="Input stream format",
    )
    parser.add_argument("--server-ip", help="Server IP in client_server mode")
    parser.add_argument("--server-port", type=int, help="Server port")
    parser.add_argument("--client-port", type=int, help="Local UDP bind port")
    parser.add_argument(
        "--listen-port",
        type=int,
        help="UDP listen port in broadcast mode",
    )
    return parser.parse_args()


def load_config(config_path: Path, explicit: bool) -> Dict[str, Any]:
    if not config_path.exists():
        if explicit:
            raise ValueError(f"Config file not found: {config_path}")
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as file_obj:
            parsed = json.load(file_obj)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in config file {config_path}: {exc}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Config file must contain a JSON object: {config_path}")

    return parsed


def validate_settings(settings: Dict[str, Any]) -> None:
    mode = settings.get("mode")
    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid mode: {mode}. Expected one of {sorted(VALID_MODES)}."
        )

    stream_format = settings.get("stream_format")
    if stream_format not in VALID_STREAM_FORMATS:
        raise ValueError(
            "Invalid stream_format: "
            f"{stream_format}. Expected one of {sorted(VALID_STREAM_FORMATS)}."
        )

    _validate_port("server_port", settings["server_port"])
    _validate_port("client_port", settings["client_port"])
    _validate_port("listen_port", settings["listen_port"])


def resolve_runtime_settings(args: argparse.Namespace) -> Dict[str, Any]:
    explicit_config = args.config is not None
    config_path = (
        Path(args.config).expanduser().resolve()
        if explicit_config
        else DEFAULT_CONFIG_PATH
    )
    config_data = load_config(config_path, explicit=explicit_config)

    settings = dict(DEFAULT_SETTINGS)
    settings["config_path"] = str(config_path)

    for key in DEFAULT_SETTINGS:
        value = config_data.get(key)
        if value is not None:
            settings[key] = value

    cli_values = {
        "mode": args.mode,
        "stream_format": args.stream_format,
        "server_ip": args.server_ip,
        "server_port": args.server_port,
        "client_port": args.client_port,
        "listen_port": args.listen_port,
    }
    for key, value in cli_values.items():
        if value is not None:
            settings[key] = value

    if isinstance(settings["mode"], str):
        settings["mode"] = settings["mode"].strip().lower()
    if isinstance(settings["stream_format"], str):
        settings["stream_format"] = settings["stream_format"].strip().lower()
    if isinstance(settings.get("server_ip"), str):
        server_ip = settings["server_ip"].strip()
        settings["server_ip"] = server_ip or None

    return settings


def prompt_interactive_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    if settings["mode"] is None:
        print("UDP Video Client")
        print("1. Client-Server Mode (connect to specific server)")
        print("2. Broadcast Mode (listen for broadcasts)")
        choice = input("Choose mode (1-2): ").strip()
        if choice == "1":
            settings["mode"] = "client_server"
        elif choice == "2":
            settings["mode"] = "broadcast"
        else:
            raise ValueError("Invalid mode choice. Expected 1 or 2.")

    if settings["mode"] == "client_server" and not settings["server_ip"]:
        server_ip = input("Enter server IP: ").strip()
        if not server_ip:
            raise ValueError("Server IP required for client_server mode.")
        settings["server_ip"] = server_ip

    return settings


def print_effective_settings(settings: Dict[str, Any]) -> None:
    print("\nEffective runtime settings:")
    print(f"  mode: {settings['mode']}")
    print(f"  stream_format: {settings['stream_format']}")
    print(f"  server_ip: {settings['server_ip']}")
    print(f"  server_port: {settings['server_port']}")
    print(f"  client_port: {settings['client_port']}")
    print(f"  listen_port: {settings['listen_port']}")
    print(f"  config_path: {settings['config_path']}\n")


def ensure_h264_dependencies() -> None:
    try:
        import av  # noqa: F401
    except ImportError as exc:
        raise ValueError(
            "stream_format='h264' requires PyAV but it is not installed.\n"
            "Install it with:\n"
            "  pip install av\n"
            "If install fails on macOS, install FFmpeg first:\n"
            "  brew install ffmpeg"
        ) from exc


class H264FrameDecoder:
    """Decode H.264 byte payloads into BGR frames."""

    def __init__(self):
        """Initialize H.264 decoder context.

        Purpose: Prepare a PyAV codec context for H.264 decoding.
        Inputs: None.
        Outputs: None. Stores decoder instance on this object.
        """
        import av

        self._codec = av.CodecContext.create("h264", "r")

    def decode_to_bgr(self, frame_data):
        """Decode raw H.264 bytes to an OpenCV-compatible frame.

        Purpose: Convert incoming encoded payload to a BGR ndarray.
        Inputs: frame_data (bytes) containing H.264 bitstream bytes.
        Outputs: numpy.ndarray in BGR format, or None when decoder emits no frame.
        """
        if not frame_data:
            return None

        frames = []
        packets = self._codec.parse(frame_data)

        # Decoder may not emit a frame on every payload.
        for packet in packets:
            frames.extend(self._codec.decode(packet))

        if not frames:
            return None

        return frames[-1].to_ndarray(format="bgr24")

class UDPVideoClient:
    """Client for client-server UDP streaming"""
    
    def __init__(
        self,
        server_host,
        server_port=9999,
        client_port=9999,
        stream_format="jpeg",
    ):
        """Initialize UDP client runtime state.

        Purpose: Configure socket/state for client-server UDP reception.
        Inputs: server_host/port, client_port, and stream_format ('jpeg'|'h264').
        Outputs: None. Initializes instance fields and binds UDP socket.
        """
        self.server_host = server_host
        self.server_port = server_port
        self.client_port = client_port  # 0 = auto-assign
        self.stream_format = stream_format
        self.running = False

        # Socket setup
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(5.0)
        
        # Bind to local port (so server knows where to send data)
        self.socket.bind(('', self.client_port))
        actual_port = self.socket.getsockname()[1]
        print(f"Client bound to port {actual_port}")
        
        # Frame reassembly for v1.1 protocol
        self.payload_size = 1200
        self.pending_frames = {}   # frame_id -> bytearray(frame_size)
        self.expected_chunks = {}  # frame_id -> remaining chunk count
        self.received_chunks = {}  # frame_id -> set of received chunk indices
        
        # Statistics tracking
        self.frames_received = 0
        self.decode_failures = 0
        self.start_time = None
        self.last_stats_time = 0
        self.h264_decoder = None
        if self.stream_format == "h264":
            self.h264_decoder = H264FrameDecoder()
        
    def send_keepalive(self):
        """Send periodic keep-alive messages"""
        while self.running:
            try:
                self.socket.sendto(b"KEEPALIVE", (self.server_host, self.server_port))
                time.sleep(5)  # Send keepalive every 5 seconds
            except:
                break
                
    def display_stats(self):
        """Display statistics every 5 seconds"""
        while self.running:
            try:
                time.sleep(5)  # Update stats every 5 seconds
                if self.running and self.start_time:
                    current_time = time.time()
                    elapsed = current_time - self.start_time
                    fps = self.frames_received / elapsed if elapsed > 0 else 0
                    
                    print(f"\n--- Video Stats ---")
                    print(f"Frames received: {self.frames_received}")
                    print(f"Decode failures: {self.decode_failures}")
                    print(f"Runtime: {elapsed:.1f}s")
                    print(f"Average FPS: {fps:.1f}")
                    print(f"------------------\n")
            except:
                break
                
    def start_receiving(self):
        """Start receiving video stream"""
        self.running = True
        
        try:
            # Get client's actual port
            client_ip, client_port = self.socket.getsockname()
            
            # Request stream start with client info
            print(f"Requesting stream from {self.server_host}:{self.server_port}")
            print(f"Client listening on port {client_port}")
            
            # Send client registration request (single-socket NAT-friendly)
            print("Registering with server...")
            self.socket.sendto(b"REGISTER_CLIENT", (self.server_host, self.server_port))
            
            # Wait for acknowledgment
            ack_data, server_addr = self.socket.recvfrom(1024)
            if ack_data == b"REGISTERED":
                print(f"Successfully registered with server {server_addr}")
            else:
                print(f"Registration failed. Server response: {ack_data}")
                return
                
            # Start keep-alive thread
            keepalive_thread = threading.Thread(target=self.send_keepalive)
            keepalive_thread.daemon = True
            keepalive_thread.start()
            
            # Start statistics thread
            stats_thread = threading.Thread(target=self.display_stats)
            stats_thread.daemon = True
            stats_thread.start()
            
            # Initialize statistics
            self.start_time = time.time()
            
            print("Receiving video stream... Press 'q' to quit")
            
            while self.running:
                try:
                    data, addr = self.socket.recvfrom(65536)
                    
                    # Skip registration acknowledgment
                    if data == b"REGISTERED":
                        continue
                    
                    # Protocol v1.1: Always-chunked format with frame_id
                    if data.startswith(b"FRAME_START"):
                        # Server uses struct.pack("LLL", frame_id, size, chunk_count)
                        # On Pi, L might be 64-bit, making packet 35 bytes: 11 + 8 + 8 + 8 = 35
                        if len(data) == 35:  # 64-bit L format
                            try:
                                frame_id, frame_size, chunk_count = struct.unpack("LLL", data[11:35])
                                if frame_size > 0:
                                    self.pending_frames[frame_id] = bytearray(frame_size)
                                    self.expected_chunks[frame_id] = chunk_count
                                    self.received_chunks[frame_id] = set()
                                    continue
                            except Exception:
                                pass
                        
                        # Fallback: try 32-bit format
                        elif len(data) >= 23:  # 32-bit format
                            try:
                                frame_id, frame_size, chunk_count = struct.unpack("III", data[11:23])
                                if frame_size > 0:
                                    self.pending_frames[frame_id] = bytearray(frame_size)
                                    self.expected_chunks[frame_id] = chunk_count
                                    self.received_chunks[frame_id] = set()
                                    continue
                            except Exception:
                                pass
                        
                    elif data.startswith(b"CHUNK"):
                        # Server uses struct.pack("LL", frame_id, chunk_index)
                        # Need to determine the header size based on L size
                        header_size = 5 + (8 * 2)  # "CHUNK" + 2 * sizeof(L) - assume 64-bit L
                        if len(data) >= header_size:
                            try:
                                frame_id, chunk_index = struct.unpack("LL", data[5:header_size])
                                payload = data[header_size:]
                                
                                if frame_id in self.pending_frames:
                                    # Avoid duplicate chunks
                                    if chunk_index not in self.received_chunks[frame_id]:
                                        offset = chunk_index * self.payload_size
                                        buf = self.pending_frames[frame_id]
                                        
                                        if offset < len(buf):
                                            end = min(offset + len(payload), len(buf))
                                            buf[offset:end] = payload[:end - offset]
                                            self.received_chunks[frame_id].add(chunk_index)
                                            
                                            # Check if frame is complete
                                            if len(self.received_chunks[frame_id]) >= self.expected_chunks[frame_id]:
                                                # Frame complete - process it
                                                frame_data = bytes(self.pending_frames.pop(frame_id))
                                                self.expected_chunks.pop(frame_id, None)
                                                self.received_chunks.pop(frame_id, None)
                                                self.process_frame_data(frame_data)
                            except Exception:
                                # Try 32-bit fallback
                                try:
                                    frame_id, chunk_index = struct.unpack("II", data[5:13])
                                    payload = data[13:]
                                    
                                    if frame_id in self.pending_frames:
                                        if chunk_index not in self.received_chunks[frame_id]:
                                            offset = chunk_index * self.payload_size
                                            buf = self.pending_frames[frame_id]
                                            
                                            if offset < len(buf):
                                                end = min(offset + len(payload), len(buf))
                                                buf[offset:end] = payload[:end - offset]
                                                self.received_chunks[frame_id].add(chunk_index)
                                                
                                                if len(self.received_chunks[frame_id]) >= self.expected_chunks[frame_id]:
                                                    frame_data = bytes(self.pending_frames.pop(frame_id))
                                                    self.expected_chunks.pop(frame_id, None)
                                                    self.received_chunks.pop(frame_id, None)
                                                    self.process_frame_data(frame_data)
                                except Exception:
                                    pass
                                    
                except socket.timeout:
                    print("Timeout waiting for data...")
                    continue
                except Exception as e:
                    print(f"Receive error: {e}")
                    break
                    
        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            # Send disconnect message to server
            try:
                print("Disconnecting from server...")
                self.socket.sendto(b"DISCONNECT", (self.server_host, self.server_port))
            except:
                pass
            self.cleanup()

    def process_frame_data(self, frame_data):
        """Process reassembled frame payload by stream format.

        Purpose: Route frame bytes to JPEG or H.264 decode pipelines.
        Inputs: frame_data (bytes) from reassembled UDP chunks.
        Outputs: None. Displays decoded frame when successful.
        """
        if self.stream_format == "jpeg":
            self.process_pickled_frame(frame_data)
            return
        if self.stream_format == "h264":
            self.process_h264_frame(frame_data)
            return
        self.decode_failures += 1
        print(f"Unsupported stream format: {self.stream_format}")
            
    def process_pickled_frame(self, pickled_data):
        """Decode and display pickled JPEG payload.

        Purpose: Preserve existing JPEG display path for compatibility.
        Inputs: pickled_data (bytes) containing pickle-serialized JPEG buffer.
        Outputs: None. Displays frame and updates frame count.
        """
        try:
            # Deserialize pickled JPEG buffer
            jpeg_buffer = pickle.loads(pickled_data)
            
            # Decode JPEG to image
            import numpy as np
            frame_array = np.frombuffer(jpeg_buffer, dtype=np.uint8)
            frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
            
            if frame is not None:
                # Increment frame counter
                self.frames_received += 1
                
                # Add frame counter overlay
                cv2.putText(frame, f"Frames: {self.frames_received}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                cv2.imshow('UDP Video Stream', frame)
                
                # Check for quit
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.running = False
        except Exception as e:
            self.decode_failures += 1
            print(f"Frame processing error: {e}")

    def process_h264_frame(self, frame_data):
        """Decode and display H.264 payload.

        Purpose: Decode H.264-encoded frame bytes using PyAV.
        Inputs: frame_data (bytes) from UDP chunk reassembly.
        Outputs: None. Displays frame and updates frame count on success.
        """
        try:
            if self.h264_decoder is None:
                raise RuntimeError("H.264 decoder is not initialized")
            frame = self.h264_decoder.decode_to_bgr(frame_data)
            if frame is None:
                return

            self.frames_received += 1
            cv2.putText(
                frame,
                f"Frames: {self.frames_received}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
            cv2.imshow('UDP Video Stream', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.running = False
        except Exception as e:
            self.decode_failures += 1
            print(f"H.264 frame processing error: {e}")
            
    def display_frame(self, compressed_data):
        """Decompress and display frame"""
        try:
            # Decompress
            frame_data = zlib.decompress(compressed_data)
            
            # Decode JPEG
            import numpy as np
            frame_array = np.frombuffer(frame_data, dtype=np.uint8)
            frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
            
            if frame is not None:
                # Increment frame counter
                self.frames_received += 1
                
                # Add frame counter overlay to video
                cv2.putText(frame, f"Frames: {self.frames_received}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                cv2.imshow('UDP Video Stream', frame)
                
                # Check for quit
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.running = False
                    
        except Exception as e:
            print(f"Frame display error: {e}")
            
    def cleanup(self):
        """Clean up resources"""
        # Display final statistics
        if self.start_time:
            elapsed = time.time() - self.start_time
            fps = self.frames_received / elapsed if elapsed > 0 else 0
            print(f"\n=== Final Statistics ===")
            print(f"Total frames received: {self.frames_received}")
            print(f"Decode failures: {self.decode_failures}")
            print(f"Total runtime: {elapsed:.1f}s")
            print(f"Average FPS: {fps:.1f}")
            print(f"========================\n")
                
        cv2.destroyAllWindows()
        self.socket.close()
        
    def stop(self):
        self.running = False

class UDPBroadcastClient:
    """Client for broadcast UDP streaming"""
    
    def __init__(self, listen_port=9999):
        self.listen_port = listen_port
        self.running = False
        
        # Socket setup
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('', listen_port))  # Listen on all interfaces
        
    def start_receiving(self):
        """Start receiving broadcast video stream"""
        self.running = True
        print(f"Listening for broadcast on port {self.listen_port}")
        print("Press 'q' to quit")
        
        last_frame_id = None
        
        while self.running:
            try:
                data, addr = self.socket.recvfrom(65536)
                
                if len(data) < 12:  # Header is 12 bytes
                    continue
                    
                # Parse header
                frame_id, timestamp = struct.unpack('!IQ', data[:12])
                compressed_data = data[12:]
                
                # Skip duplicate frames (simple approach)
                if frame_id == last_frame_id:
                    continue
                last_frame_id = frame_id
                
                # Decompress and display
                try:
                    frame_data = zlib.decompress(compressed_data)
                    
                    import numpy as np
                    frame_array = np.frombuffer(frame_data, dtype=np.uint8)
                    frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        # Add frame info overlay
                        cv2.putText(frame, f"Frame: {frame_id}", (10, 30), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        cv2.putText(frame, f"From: {addr[0]}", (10, 60), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        cv2.imshow('UDP Broadcast Stream', frame)
                    
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            break
                        
                except Exception as e:
                    print(f"Frame decode error: {e}")
                    
            except Exception as e:
                print(f"Receive error: {e}")
                break
                
        self.cleanup()
        
    def cleanup(self):
        """Clean up resources"""
        cv2.destroyAllWindows()
        self.socket.close()
        
    def stop(self):
        self.running = False

def main() -> int:
    try:
        args = parse_args()
        settings = resolve_runtime_settings(args)

        if settings["mode"] is None or (
            settings["mode"] == "client_server" and not settings["server_ip"]
        ):
            if not sys.stdin.isatty():
                raise ValueError(
                    "Missing required runtime values in non-interactive mode. "
                    "Provide --mode and --server-ip (for client_server mode) "
                    "or set them in config."
                )
            settings = prompt_interactive_settings(settings)

        validate_settings(settings)
        print_effective_settings(settings)

        if settings["stream_format"] == "h264":
            ensure_h264_dependencies()

        client = None
        if settings["mode"] == "client_server":
            client = UDPVideoClient(
                settings["server_ip"],
                settings["server_port"],
                settings["client_port"],
                settings["stream_format"],
            )
            client.start_receiving()
        elif settings["mode"] == "broadcast":
            client = UDPBroadcastClient(listen_port=settings["listen_port"])
            client.start_receiving()
        return 0
    except KeyboardInterrupt:
        print("\nStopping client...")
        return 130
    except Exception as exc:
        print(f"Client error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())