#!/usr/bin/env python3
"""
Enhanced UDP Video Client - Uses advanced video display capabilities
"""

import argparse
import cv2
import json
from pathlib import Path
import socket
import struct
import time
import threading
import numpy as np
from video_display import VideoDisplay, MultiWindowDisplay
from main import H264FrameDecoder, ensure_h264_dependencies

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config" / "config.json"


class EnhancedUDPVideoClient:
    """Enhanced UDP Video Client with advanced display options"""
    
    def __init__(
        self,
        server_host,
        server_port=9999,
        client_port=0,
        display_mode="single",
        stream_format="jpeg",
    ):
        """Initialize enhanced UDP client.

        Purpose: Configure enhanced receiver display and UDP networking state.
        Inputs: server host/port, client bind port, display mode, stream format.
        Outputs: None. Prepares socket, display objects, and decode helpers.
        """
        self.server_host = server_host
        self.server_port = server_port
        self.client_port = client_port
        self.stream_format = stream_format
        self.running = False
        
        # Socket setup
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if client_port:
            self.socket.bind(('', client_port))
        else:
            self.socket.bind(('', 0))
            self.client_port = self.socket.getsockname()[1]
            
        print(f"Client bound to port {self.client_port}")
        
        # Frame handling (aligned with v1.1 chunk protocol)
        self.payload_size = 1200
        self.pending_frames = {}
        self.expected_chunks = {}
        self.received_chunks = {}
        
        # Statistics
        self.frames_received = 0
        self.decode_failures = 0
        self.start_time = None
        self.last_stats_time = None
        self.h264_decoder = None
        if self.stream_format == "h264":
            self.h264_decoder = H264FrameDecoder()
        
        # Display setup
        self.display_mode = display_mode
        if display_mode == "single":
            self.display = VideoDisplay("Enhanced UDP Video Stream", (1024, 768))
            self.display.on_key_press = self._handle_key_press
        elif display_mode == "multi":
            self.multi_display = MultiWindowDisplay()
            self.main_display = self.multi_display.add_display("main", "Main Stream", (800, 600))
            self.mini_display = self.multi_display.add_display("mini", "Mini View", (400, 300))
            self.stats_display = self.multi_display.add_display("stats", "Statistics", (300, 200))
            
            # Set key handlers
            self.main_display.on_key_press = self._handle_key_press
            self.mini_display.on_key_press = self._handle_key_press
            
        # Threading
        self.stats_thread = None
        
    def _handle_key_press(self, key):
        """Handle key presses from display windows"""
        if key == ord('q') or key == 27:  # Quit
            self.running = False
            return True
        elif key == ord('m'):  # Switch display mode
            print("Display mode switching not implemented during runtime")
        elif key == ord('p'):  # Print current stats
            self._print_current_stats()
            
        return False
        
    def _print_current_stats(self):
        """Print current statistics"""
        if self.start_time:
            runtime = time.time() - self.start_time
            fps = self.frames_received / runtime if runtime > 0 else 0
            print(f"\n=== Current Stats ===")
            print(f"Frames received: {self.frames_received}")
            print(f"Runtime: {runtime:.1f}s")
            print(f"Current FPS: {fps:.1f}")
            print(f"==================\n")
        
    def start_receiving(self):
        """Start receiving video stream"""
        try:
            print(f"Requesting stream from {self.server_host}:{self.server_port}")
            print(f"Client listening on port {self.client_port}")
            
            # Register with server
            print("Registering with server...")
            self.socket.sendto(b"REGISTER_CLIENT", (self.server_host, self.server_port))
            
            # Wait for acknowledgment
            self.socket.settimeout(5.0)
            data, addr = self.socket.recvfrom(1024)
            if data == b"REGISTERED":
                print(f"Successfully registered with server {addr}")
            else:
                print(f"Unexpected response: {data}")
                return
                
            self.socket.settimeout(1.0)
            self.running = True
            
            # Start display
            if self.display_mode == "single":
                self.display.start()
            elif self.display_mode == "multi":
                self.multi_display.start_all()
            
            # Start statistics thread
            self.stats_thread = threading.Thread(target=self.display_stats, daemon=True)
            self.stats_thread.start()
            
            # Initialize statistics
            self.start_time = time.time()
            self.last_stats_time = time.time()
            
            print("Receiving video stream... Press 'h' in video window for help")
            
            while self.running:
                try:
                    data, addr = self.socket.recvfrom(65536)
                    
                    if data == b"REGISTERED":
                        continue

                    if data.startswith(b"FRAME_START"):
                        if len(data) == 35:
                            try:
                                frame_id, frame_size, chunk_count = struct.unpack(
                                    "LLL", data[11:35]
                                )
                                if frame_size > 0:
                                    self.pending_frames[frame_id] = bytearray(frame_size)
                                    self.expected_chunks[frame_id] = chunk_count
                                    self.received_chunks[frame_id] = set()
                                    continue
                            except Exception:
                                pass
                        elif len(data) >= 23:
                            try:
                                frame_id, frame_size, chunk_count = struct.unpack(
                                    "III", data[11:23]
                                )
                                if frame_size > 0:
                                    self.pending_frames[frame_id] = bytearray(frame_size)
                                    self.expected_chunks[frame_id] = chunk_count
                                    self.received_chunks[frame_id] = set()
                                    continue
                            except Exception:
                                pass

                    elif data.startswith(b"CHUNK"):
                        header_size = 5 + (8 * 2)
                        if len(data) >= header_size:
                            try:
                                frame_id, chunk_index = struct.unpack(
                                    "LL", data[5:header_size]
                                )
                                payload = data[header_size:]
                                if frame_id in self.pending_frames:
                                    if chunk_index not in self.received_chunks[frame_id]:
                                        offset = chunk_index * self.payload_size
                                        buf = self.pending_frames[frame_id]
                                        if offset < len(buf):
                                            end = min(offset + len(payload), len(buf))
                                            buf[offset:end] = payload[:end - offset]
                                            self.received_chunks[frame_id].add(chunk_index)
                                            if (
                                                len(self.received_chunks[frame_id])
                                                >= self.expected_chunks[frame_id]
                                            ):
                                                frame_data = bytes(
                                                    self.pending_frames.pop(frame_id)
                                                )
                                                self.expected_chunks.pop(frame_id, None)
                                                self.received_chunks.pop(frame_id, None)
                                                self.process_frame_data(frame_data)
                            except Exception:
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
                                                if (
                                                    len(self.received_chunks[frame_id])
                                                    >= self.expected_chunks[frame_id]
                                                ):
                                                    frame_data = bytes(
                                                        self.pending_frames.pop(frame_id)
                                                    )
                                                    self.expected_chunks.pop(frame_id, None)
                                                    self.received_chunks.pop(frame_id, None)
                                                    self.process_frame_data(frame_data)
                                except Exception:
                                    pass
                                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Receive error: {e}")
                    break
                    
        finally:
            try:
                print("Disconnecting from server...")
                self.socket.sendto(b"DISCONNECT", (self.server_host, self.server_port))
            except:
                pass
            self.cleanup()

    def process_frame_data(self, frame_data):
        """Route frame payload by selected stream format.

        Purpose: Keep enhanced display path compatible for JPEG and H.264 modes.
        Inputs: frame_data bytes for one fully reassembled frame payload.
        Outputs: None. Updates display and counters.
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

        Purpose: Preserve legacy JPEG mode in enhanced display client.
        Inputs: pickled_data (bytes) representing pickle-serialized JPEG bytes.
        Outputs: None. Updates enhanced display windows.
        """
        try:
            # Deserialize pickled JPEG buffer
            import pickle
            jpeg_buffer = pickle.loads(pickled_data)
            
            # Decode JPEG to image
            import numpy as np
            frame_array = np.frombuffer(jpeg_buffer, dtype=np.uint8)
            frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
            
            if frame is not None:
                # Increment frame counter
                self.frames_received += 1
                
                # Update display(s)
                if self.display_mode == "single":
                    self.display.update_frame(frame)
                elif self.display_mode == "multi":
                    # Main display gets full frame
                    self.main_display.update_frame(frame)
                    
                    # Mini display gets resized frame
                    mini_frame = cv2.resize(frame, (320, 240))
                    self.mini_display.update_frame(mini_frame)
                    
                    # Stats display gets a statistics overlay
                    self._update_stats_display()
                    
        except Exception as e:
            self.decode_failures += 1
            print(f"Frame processing error: {e}")

    def process_h264_frame(self, frame_data):
        """Decode and display H.264 payload.

        Purpose: Render H.264 frames with enhanced single/multi-window display.
        Inputs: frame_data bytes from UDP reassembly.
        Outputs: None. Updates display windows and counters.
        """
        try:
            if self.h264_decoder is None:
                raise RuntimeError("H.264 decoder is not initialized")
            frame = self.h264_decoder.decode_to_bgr(frame_data)
            if frame is None:
                return

            self.frames_received += 1
            if self.display_mode == "single":
                self.display.update_frame(frame)
            elif self.display_mode == "multi":
                self.main_display.update_frame(frame)
                mini_frame = cv2.resize(frame, (320, 240))
                self.mini_display.update_frame(mini_frame)
                self._update_stats_display()
        except Exception as e:
            self.decode_failures += 1
            print(f"H.264 frame processing error: {e}")
            
    def _update_stats_display(self):
        """Update the statistics display window"""
        if not hasattr(self, 'stats_display'):
            return
            
        # Create stats visualization
        stats_frame = np.zeros((200, 300, 3), dtype=np.uint8)
        
        # Add text information
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        color = (0, 255, 0)
        thickness = 1
        
        runtime = time.time() - self.start_time if self.start_time else 0
        fps = self.frames_received / runtime if runtime > 0 else 0
        
        texts = [
            f"Frames: {self.frames_received}",
            f"Format: {self.stream_format}",
            f"Runtime: {runtime:.1f}s",
            f"FPS: {fps:.1f}",
            f"Server: {self.server_host}",
            f"Port: {self.server_port}",
        ]
        
        y_offset = 30
        for text in texts:
            cv2.putText(stats_frame, text, (10, y_offset), font, font_scale, color, thickness)
            y_offset += 25
            
        self.stats_display.update_frame(stats_frame)
        
    def display_stats(self):
        """Display periodic statistics"""
        while self.running:
            time.sleep(5.0)
            if self.running and self.start_time:
                runtime = time.time() - self.start_time
                fps = self.frames_received / runtime if runtime > 0 else 0
                
                print(f"\n--- Video Stats ---")
                print(f"Frames received: {self.frames_received}")
                print(f"Decode failures: {self.decode_failures}")
                print(f"Runtime: {runtime:.1f}s")
                print(f"Average FPS: {fps:.1f}")
                print(f"------------------\n")
                
    def cleanup(self):
        """Clean up resources"""
        print("\n=== Final Statistics ===")
        if self.start_time:
            total_runtime = time.time() - self.start_time
            avg_fps = self.frames_received / total_runtime if total_runtime > 0 else 0
            print(f"Total frames received: {self.frames_received}")
            print(f"Decode failures: {self.decode_failures}")
            print(f"Total runtime: {total_runtime:.1f}s")
            print(f"Average FPS: {avg_fps:.1f}")
        print("========================\n")
        
        # Stop displays
        if self.display_mode == "single" and hasattr(self, 'display'):
            self.display.stop()
        elif self.display_mode == "multi" and hasattr(self, 'multi_display'):
            self.multi_display.stop_all()
            
        # Close socket
        try:
            self.socket.close()
        except:
            pass
            
        print("Stopping client...")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for enhanced receiver entrypoint.

    Purpose: Accept optional config and stream-format compatible flags.
    Inputs: CLI arguments from argv.
    Outputs: argparse.Namespace with parsed option values.
    """
    parser = argparse.ArgumentParser(description="Enhanced UDP Video Client")
    parser.add_argument("--config", help="Path to receiver JSON config file")
    parser.add_argument(
        "--display-mode",
        choices=["single", "multi"],
        help="Enhanced display mode",
    )
    parser.add_argument(
        "--stream-format",
        choices=["jpeg", "h264"],
        help="Input stream format",
    )
    parser.add_argument("--server-ip", help="Server IP")
    parser.add_argument("--server-port", type=int, help="Server port")
    parser.add_argument("--client-port", type=int, help="Client UDP bind port")
    return parser.parse_args()


def load_config(config_path: Path) -> dict:
    """Load optional JSON config for enhanced entrypoint.

    Purpose: Provide defaults aligned with receiver main config behavior.
    Inputs: config_path to JSON file.
    Outputs: dict with config values; empty dict when file is absent.
    """
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    return data if isinstance(data, dict) else {}


def main():
    """Run enhanced UDP client entrypoint.

    Purpose: Start enhanced receiver with CLI/config pass-through support.
    Inputs: Runtime CLI/config values for network, format, and display mode.
    Outputs: None. Starts receiving loop until stopped.
    """
    print("Enhanced UDP Video Client")
    print("1. Single Window Mode")
    print("2. Multi-Window Mode")

    try:
        args = parse_args()
        config_path = (
            Path(args.config).expanduser().resolve()
            if args.config
            else DEFAULT_CONFIG_PATH
        )
        config = load_config(config_path)

        display_mode = args.display_mode or config.get("display_mode")
        if display_mode not in {"single", "multi"}:
            mode_choice = input("Choose display mode (1-2): ").strip()
            display_mode = "multi" if mode_choice == "2" else "single"

        stream_format = (args.stream_format or config.get("stream_format") or "jpeg").lower()
        if stream_format not in {"jpeg", "h264"}:
            raise ValueError("stream_format must be one of: jpeg, h264")
        if stream_format == "h264":
            ensure_h264_dependencies()

        server_ip = args.server_ip or config.get("server_ip")
        if not server_ip:
            server_ip = input("Enter server IP: ").strip()
        if not server_ip:
            raise ValueError("Server IP is required")

        server_port = args.server_port or config.get("server_port") or 9999
        client_port = args.client_port
        if client_port is None:
            client_port = config.get("client_port", 0)

        client = EnhancedUDPVideoClient(
            server_ip,
            int(server_port),
            int(client_port),
            display_mode,
            stream_format,
        )

        print(f"\nStarting in {display_mode} mode ({stream_format})...")
        if display_mode == "multi":
            print("Multiple windows will open:")
            print("- Main Stream: Full video display")
            print("- Mini View: Smaller video display")
            print("- Statistics: Real-time stats")

        client.start_receiving()

    except KeyboardInterrupt:
        print("\nShutdown requested...")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
