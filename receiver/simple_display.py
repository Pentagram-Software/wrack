#!/usr/bin/env python3
"""
Simple Video Display Module - Basic enhanced video display for UDP video streams
"""

import cv2
import numpy as np
import time
from typing import Optional


class SimpleVideoDisplay:
    """Simple enhanced video display without threading complications"""
    
    def __init__(self, window_name="Enhanced Video Stream", window_size=(800, 600)):
        self.window_name = window_name
        self.window_size = window_size
        self.window_created = False
        
        # Display settings
        self.show_fps = True
        self.show_frame_count = True
        self.show_timestamp = True
        self.show_resolution = True
        self.show_runtime = True
        
        # Statistics
        self.frames_displayed = 0
        self.start_time = time.time()
        self.last_fps_time = time.time()
        self.fps_counter = 0
        self.current_fps = 0.0
        
        # Window state
        self.fullscreen = False
        
    def create_window(self):
        """Create the display window"""
        if not self.window_created:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.window_name, *self.window_size)
            self.window_created = True
            self.start_time = time.time()
            self.last_fps_time = time.time()
            
    def display_frame(self, frame):
        """Display a frame with overlays"""
        if frame is None:
            return False
            
        # Create window if not exists
        self.create_window()
        
        # Update statistics
        self.frames_displayed += 1
        self.fps_counter += 1
        
        current_time = time.time()
        if current_time - self.last_fps_time >= 1.0:
            self.current_fps = self.fps_counter / (current_time - self.last_fps_time)
            self.fps_counter = 0
            self.last_fps_time = current_time
            
        # Add overlays
        display_frame = self._add_overlays(frame.copy())
        
        # Display frame
        cv2.imshow(self.window_name, display_frame)
        
        # Handle key presses
        key = cv2.waitKey(1) & 0xFF
        return self._handle_key(key)
        
    def _add_overlays(self, frame):
        """Add information overlays to the frame"""
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        color = (0, 255, 0)  # Green
        thickness = 2
        line_height = 25
        y_offset = 25
        
        # Frame count
        if self.show_frame_count:
            text = f"Frames: {self.frames_displayed}"
            cv2.putText(frame, text, (10, y_offset), font, font_scale, color, thickness)
            y_offset += line_height
            
        # FPS
        if self.show_fps:
            text = f"FPS: {self.current_fps:.1f}"
            cv2.putText(frame, text, (10, y_offset), font, font_scale, color, thickness)
            y_offset += line_height
            
        # Resolution
        if self.show_resolution:
            h, w = frame.shape[:2]
            text = f"Resolution: {w}x{h}"
            cv2.putText(frame, text, (10, y_offset), font, font_scale, color, thickness)
            y_offset += line_height
            
        # Timestamp
        if self.show_timestamp:
            current_time = time.strftime("%H:%M:%S")
            text = f"Time: {current_time}"
            cv2.putText(frame, text, (10, y_offset), font, font_scale, color, thickness)
            
        # Runtime in top-right corner
        if self.show_runtime:
            runtime = time.time() - self.start_time
            runtime_text = f"Runtime: {runtime:.1f}s"
            text_size = cv2.getTextSize(runtime_text, font, font_scale, thickness)[0]
            cv2.putText(frame, runtime_text, 
                       (frame.shape[1] - text_size[0] - 10, 25), 
                       font, font_scale, color, thickness)
                       
        return frame
        
    def _handle_key(self, key):
        """Handle keyboard input - returns True if should quit"""
        if key == ord('q') or key == 27:  # 'q' or ESC
            return True
        elif key == ord('f'):  # Toggle fullscreen
            self.toggle_fullscreen()
        elif key == ord('s'):  # Save screenshot
            self.save_screenshot()
        elif key == ord('r'):  # Reset statistics
            self.reset_stats()
        elif key == ord('h'):  # Show help
            self.show_help()
        elif key == ord('1'):  # Toggle frame count
            self.show_frame_count = not self.show_frame_count
            print(f"Frame count display: {'ON' if self.show_frame_count else 'OFF'}")
        elif key == ord('2'):  # Toggle FPS
            self.show_fps = not self.show_fps
            print(f"FPS display: {'ON' if self.show_fps else 'OFF'}")
        elif key == ord('3'):  # Toggle timestamp
            self.show_timestamp = not self.show_timestamp
            print(f"Timestamp display: {'ON' if self.show_timestamp else 'OFF'}")
        elif key == ord('4'):  # Toggle resolution
            self.show_resolution = not self.show_resolution
            print(f"Resolution display: {'ON' if self.show_resolution else 'OFF'}")
        elif key == ord('5'):  # Toggle runtime
            self.show_runtime = not self.show_runtime
            print(f"Runtime display: {'ON' if self.show_runtime else 'OFF'}")
        elif key == ord('p'):  # Print stats
            self.print_stats()
            
        return False
        
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if not self.window_created:
            return
            
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            print("Fullscreen mode ON")
        else:
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.window_name, *self.window_size)
            print("Fullscreen mode OFF")
            
    def save_screenshot(self):
        """Save current frame as screenshot"""
        # This would need the current frame to be stored
        print("Screenshot feature requires frame storage - not implemented in this simple version")
        
    def reset_stats(self):
        """Reset display statistics"""
        self.frames_displayed = 0
        self.start_time = time.time()
        self.last_fps_time = time.time()
        self.fps_counter = 0
        self.current_fps = 0.0
        print("Statistics reset")
        
    def print_stats(self):
        """Print current statistics"""
        runtime = time.time() - self.start_time
        avg_fps = self.frames_displayed / runtime if runtime > 0 else 0
        
        print(f"\n=== Display Statistics ===")
        print(f"Frames displayed: {self.frames_displayed}")
        print(f"Runtime: {runtime:.1f}s")
        print(f"Current FPS: {self.current_fps:.1f}")
        print(f"Average FPS: {avg_fps:.1f}")
        print(f"========================\n")
        
    def show_help(self):
        """Display help information"""
        help_text = """
=== Video Display Controls ===
q/ESC : Quit
f     : Toggle fullscreen
s     : Save screenshot (not implemented)
r     : Reset statistics
h     : Show this help
p     : Print current statistics
1     : Toggle frame count display
2     : Toggle FPS display
3     : Toggle timestamp display
4     : Toggle resolution display
5     : Toggle runtime display
=============================
        """
        print(help_text)
        
    def cleanup(self):
        """Clean up resources"""
        if self.window_created:
            cv2.destroyWindow(self.window_name)
            self.window_created = False


# Example integration with existing UDP client
if __name__ == "__main__":
    import sys
    import os
    import argparse
    import json
    from pathlib import Path
    
    # Add current directory to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    try:
        from main import (
            UDPVideoClient,
            H264FrameDecoder,
            ensure_h264_dependencies,
            DEFAULT_CONFIG_PATH,
        )
        import pickle
        
        class UDPClientWithSimpleDisplay(UDPVideoClient):
            """UDP client with simple enhanced display"""
            
            def __init__(
                self,
                server_host,
                server_port=9999,
                client_port=0,
                stream_format="jpeg",
            ):
                """Initialize simple-display UDP client.

                Purpose: Use SimpleVideoDisplay with base UDP receiver behavior.
                Inputs: server settings and selected stream_format.
                Outputs: None. Initializes receiver and display components.
                """
                super().__init__(server_host, server_port, client_port, stream_format)
                self.display = SimpleVideoDisplay("Simple Enhanced Stream", (1024, 768))
                
            def process_pickled_frame(self, pickled_data):
                """Process JPEG payload in simple display mode.

                Purpose: Decode JPEG payload and render with overlays.
                Inputs: pickled_data containing pickle-serialized JPEG bytes.
                Outputs: None. Updates display and frame counters.
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
                        
                        # Display frame with enhancements
                        should_quit = self.display.display_frame(frame)
                        if should_quit:
                            self.running = False
                            
                except Exception as e:
                    print(f"Frame processing error: {e}")

            def process_h264_frame(self, frame_data):
                """Process H.264 payload in simple display mode.

                Purpose: Decode H.264 bytes and render with overlays.
                Inputs: frame_data bytes from reassembled UDP chunks.
                Outputs: None. Updates display and frame counters.
                """
                try:
                    if self.h264_decoder is None:
                        self.h264_decoder = H264FrameDecoder()
                    frame = self.h264_decoder.decode_to_bgr(frame_data)
                    if frame is None:
                        return
                    self.frames_received += 1
                    should_quit = self.display.display_frame(frame)
                    if should_quit:
                        self.running = False
                except Exception as e:
                    self.decode_failures += 1
                    print(f"H.264 frame processing error: {e}")
                    
            def cleanup(self):
                """Override cleanup"""
                self.display.cleanup()
                super().cleanup()
        
        # Demo
        print("Simple Enhanced UDP Video Client")
        print("Features: FPS display, frame counter, timestamp, resolution, runtime")
        print("Press 'h' in video window for help")
        print()

        parser = argparse.ArgumentParser(description="Simple display UDP client")
        parser.add_argument("--config", help="Path to receiver JSON config file")
        parser.add_argument(
            "--stream-format",
            choices=["jpeg", "h264"],
            help="Input stream format",
        )
        parser.add_argument("--server-ip", help="Server IP")
        parser.add_argument("--server-port", type=int, help="Server port")
        parser.add_argument("--client-port", type=int, help="Client UDP bind port")
        args = parser.parse_args()

        config_path = (
            Path(args.config).expanduser().resolve()
            if args.config
            else DEFAULT_CONFIG_PATH
        )
        config = {}
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as file_obj:
                parsed = json.load(file_obj)
                if isinstance(parsed, dict):
                    config = parsed

        stream_format = (args.stream_format or config.get("stream_format") or "jpeg").lower()
        if stream_format == "h264":
            ensure_h264_dependencies()

        server_ip = args.server_ip or config.get("server_ip")
        if not server_ip:
            server_ip = input("Enter server IP: ").strip()
        if not server_ip:
            print("Server IP is required")
            sys.exit(1)

        server_port = int(args.server_port or config.get("server_port") or 9999)
        client_port = int(
            args.client_port
            if args.client_port is not None
            else config.get("client_port", 0)
        )

        client = UDPClientWithSimpleDisplay(
            server_ip,
            server_port,
            client_port,
            stream_format,
        )
        client.start_receiving()
        
    except ImportError:
        print("Could not import main UDP client - running in demo mode")
        
        # Simple demo
        display = SimpleVideoDisplay("Demo Display", (640, 480))
        
        print("Demo mode: Generating test pattern")
        print("Press 'h' for help, 'q' to quit")
        
        frame_count = 0
        try:
            while True:
                # Create test pattern
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                
                # Add some content
                cv2.rectangle(frame, (50, 50), (590, 430), (100, 100, 255), 2)
                cv2.putText(frame, f"Demo Frame {frame_count}", (60, 250), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                
                # Display frame
                should_quit = display.display_frame(frame)
                if should_quit:
                    break
                    
                frame_count += 1
                time.sleep(1/30)  # 30 FPS
                
        except KeyboardInterrupt:
            pass
        finally:
            display.cleanup()
    
    except Exception as e:
        print(f"Error: {e}")
