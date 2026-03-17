#!/usr/bin/env python3
"""
Example: How to integrate the VideoDisplay module with existing UDP client
"""

import sys
import os
import argparse
import json
from pathlib import Path

# Add current directory to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import (
    UDPVideoClient,
    H264FrameDecoder,
    ensure_h264_dependencies,
    DEFAULT_CONFIG_PATH,
)
from video_display import VideoDisplay
import cv2


class UDPClientWithEnhancedDisplay(UDPVideoClient):
    """Extended UDP client that uses the enhanced video display"""
    
    def __init__(
        self,
        server_host,
        server_port=9999,
        client_port=0,
        stream_format="jpeg",
    ):
        """Initialize enhanced display wrapper over UDPVideoClient.

        Purpose: Reuse base UDP receiver while overriding display behavior.
        Inputs: server settings and selected stream_format.
        Outputs: None. Initializes parent receiver and display settings.
        """
        super().__init__(server_host, server_port, client_port, stream_format)
        
        # Replace the basic display with enhanced display
        self.video_display = VideoDisplay("Enhanced Stream View", (1024, 768))
        self.video_display.show_fps = True
        self.video_display.show_frame_count = True
        self.video_display.show_timestamp = True
        self.video_display.show_resolution = True
        
        # Set up custom key handler
        self.video_display.on_key_press = self._handle_display_keys
        
    def _handle_display_keys(self, key):
        """Handle keys from the video display"""
        if key == ord('q') or key == 27:  # Quit
            self.running = False
            return True
        elif key == ord('p'):  # Print stats
            self._print_stats()
        return False
        
    def _print_stats(self):
        """Print current statistics"""
        stats = self.video_display.get_stats()
        print(f"\n=== Display Statistics ===")
        print(f"Frames displayed: {stats['frames_displayed']}")
        print(f"Display runtime: {stats['runtime']:.1f}s")
        print(f"Current FPS: {stats['current_fps']:.1f}")
        print(f"Average FPS: {stats['average_fps']:.1f}")
        print(f"========================\n")
        
    def start_receiving(self):
        """Override to start the enhanced display"""
        # Start the video display
        self.video_display.start()
        
        # Call parent's start_receiving method
        super().start_receiving()
        
    def process_pickled_frame(self, pickled_data):
        """Process JPEG payload using enhanced display.

        Purpose: Preserve JPEG rendering path with VideoDisplay overlays.
        Inputs: pickled_data containing pickle-wrapped JPEG bytes.
        Outputs: None. Updates display and frame counters.
        """
        try:
            # Deserialize pickled JPEG buffer
            import pickle
            import numpy as np
            
            jpeg_buffer = pickle.loads(pickled_data)
            
            # Decode JPEG to image
            frame_array = np.frombuffer(jpeg_buffer, dtype=np.uint8)
            frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
            
            if frame is not None:
                # Increment frame counter
                self.frames_received += 1
                
                # Update the enhanced display
                self.video_display.update_frame(frame)
                
                # Check if display is still running
                if not self.video_display.running:
                    self.running = False
                    
        except Exception as e:
            print(f"Frame processing error: {e}")

    def process_h264_frame(self, frame_data):
        """Process H.264 payload using enhanced display.

        Purpose: Render decoded H.264 frames in VideoDisplay.
        Inputs: frame_data bytes for one reassembled frame.
        Outputs: None. Updates display and frame counters.
        """
        try:
            if self.h264_decoder is None:
                self.h264_decoder = H264FrameDecoder()
            frame = self.h264_decoder.decode_to_bgr(frame_data)
            if frame is None:
                return
            self.frames_received += 1
            self.video_display.update_frame(frame)
            if not self.video_display.running:
                self.running = False
        except Exception as e:
            self.decode_failures += 1
            print(f"H.264 frame processing error: {e}")
            
    def cleanup(self):
        """Override cleanup to stop enhanced display"""
        # Stop the video display
        if hasattr(self, 'video_display'):
            self.video_display.stop()
            
        # Call parent cleanup
        super().cleanup()


def main():
    """Run enhanced display example client.

    Purpose: Start display-example client with config/format pass-through.
    Inputs: CLI/config runtime options for server and stream format.
    Outputs: None. Starts receiving loop until stopped.
    """
    print("UDP Video Client with Enhanced Display")
    print("Enhanced features:")
    print("- Resizable window")
    print("- Real-time FPS display")
    print("- Frame counter overlay")
    print("- Timestamp display")
    print("- Screenshot capability (press 's')")
    print("- Fullscreen toggle (press 'f')")
    print("- Statistics reset (press 'r')")
    print("- Help display (press 'h')")
    print()
    
    parser = argparse.ArgumentParser(description="Display example UDP client")
    parser.add_argument("--config", help="Path to receiver JSON config file")
    parser.add_argument(
        "--stream-format",
        choices=["jpeg", "h264"],
        help="Input stream format",
    )
    parser.add_argument("--server-ip", help="Server IP")
    parser.add_argument("--server-port", type=int, help="Server port")
    parser.add_argument("--client-port", type=int, help="Client UDP bind port")

    try:
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
            return

        server_port = int(args.server_port or config.get("server_port") or 9999)
        client_port = int(args.client_port if args.client_port is not None else config.get("client_port", 0))

        client = UDPClientWithEnhancedDisplay(
            server_ip,
            server_port,
            client_port,
            stream_format,
        )
        client.start_receiving()
        
    except KeyboardInterrupt:
        print("\nShutdown requested...")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
