#!/usr/bin/env python3
"""
Video Display Module - Enhanced video display capabilities for UDP video streams
"""

import cv2
import numpy as np
import time
import threading
from typing import Optional, Callable


class VideoDisplay:
    """Enhanced video display with additional features"""
    
    def __init__(self, window_name="UDP Video Stream", window_size=(800, 600)):
        self.window_name = window_name
        self.window_size = window_size
        self.current_frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.display_thread = None
        
        # Display settings
        self.show_fps = True
        self.show_frame_count = True
        self.show_timestamp = True
        self.show_resolution = True
        self.fullscreen = False
        
        # Statistics
        self.frames_displayed = 0
        self.start_time = time.time()
        self.last_fps_time = time.time()
        self.fps_counter = 0
        self.current_fps = 0.0
        
        # Callbacks
        self.on_key_press: Optional[Callable[[int], bool]] = None
        
    def start(self):
        """Start the video display in a separate thread"""
        if self.running:
            return
            
        self.running = True
        self.start_time = time.time()
        self.last_fps_time = time.time()
        
        # Create window
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, *self.window_size)
        
        # Start display thread
        self.display_thread = threading.Thread(target=self._display_loop, daemon=True)
        self.display_thread.start()
        
    def stop(self):
        """Stop the video display"""
        self.running = False
        if self.display_thread:
            self.display_thread.join(timeout=1.0)
        cv2.destroyWindow(self.window_name)
        
    def update_frame(self, frame):
        """Update the current frame to display"""
        if frame is None:
            return
            
        with self.frame_lock:
            self.current_frame = frame.copy()
            self.frames_displayed += 1
            
        # Update FPS calculation
        self.fps_counter += 1
        current_time = time.time()
        if current_time - self.last_fps_time >= 1.0:
            self.current_fps = self.fps_counter / (current_time - self.last_fps_time)
            self.fps_counter = 0
            self.last_fps_time = current_time
            
    def _display_loop(self):
        """Main display loop running in separate thread"""
        while self.running:
            try:
                with self.frame_lock:
                    if self.current_frame is not None:
                        display_frame = self.current_frame.copy()
                    else:
                        display_frame = None
                        
                if display_frame is not None:
                    # Add overlays
                    display_frame = self._add_overlays(display_frame)
                    
                    # Display frame
                    cv2.imshow(self.window_name, display_frame)
                    
                # Handle key presses
                key = cv2.waitKey(1) & 0xFF
                if key != 255:  # Key was pressed
                    if self._handle_key(key):
                        break
                        
            except Exception as e:
                print(f"Display error: {e}")
                
            time.sleep(0.001)  # Small delay to prevent excessive CPU usage
            
    def _add_overlays(self, frame):
        """Add information overlays to the frame"""
        overlay_frame = frame.copy()
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        color = (0, 255, 0)  # Green
        thickness = 2
        line_height = 25
        y_offset = 25
        
        # Frame count
        if self.show_frame_count:
            text = f"Frames: {self.frames_displayed}"
            cv2.putText(overlay_frame, text, (10, y_offset), font, font_scale, color, thickness)
            y_offset += line_height
            
        # FPS
        if self.show_fps:
            text = f"FPS: {self.current_fps:.1f}"
            cv2.putText(overlay_frame, text, (10, y_offset), font, font_scale, color, thickness)
            y_offset += line_height
            
        # Resolution
        if self.show_resolution:
            h, w = frame.shape[:2]
            text = f"Resolution: {w}x{h}"
            cv2.putText(overlay_frame, text, (10, y_offset), font, font_scale, color, thickness)
            y_offset += line_height
            
        # Timestamp
        if self.show_timestamp:
            current_time = time.strftime("%H:%M:%S")
            text = f"Time: {current_time}"
            cv2.putText(overlay_frame, text, (10, y_offset), font, font_scale, color, thickness)
            
        # Runtime in top-right corner
        runtime = time.time() - self.start_time
        runtime_text = f"Runtime: {runtime:.1f}s"
        text_size = cv2.getTextSize(runtime_text, font, font_scale, thickness)[0]
        cv2.putText(overlay_frame, runtime_text, 
                   (frame.shape[1] - text_size[0] - 10, 25), 
                   font, font_scale, color, thickness)
                   
        return overlay_frame
        
    def _handle_key(self, key):
        """Handle keyboard input"""
        # Call custom key handler if set
        if self.on_key_press and self.on_key_press(key):
            return True
            
        # Built-in key handlers
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
        elif key == ord('2'):  # Toggle FPS
            self.show_fps = not self.show_fps
        elif key == ord('3'):  # Toggle timestamp
            self.show_timestamp = not self.show_timestamp
        elif key == ord('4'):  # Toggle resolution
            self.show_resolution = not self.show_resolution
            
        return False
        
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        else:
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.window_name, *self.window_size)
            
    def save_screenshot(self):
        """Save current frame as screenshot"""
        with self.frame_lock:
            if self.current_frame is not None:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.jpg"
                cv2.imwrite(filename, self.current_frame)
                print(f"Screenshot saved: {filename}")
            else:
                print("No frame to save")
                
    def reset_stats(self):
        """Reset display statistics"""
        self.frames_displayed = 0
        self.start_time = time.time()
        self.last_fps_time = time.time()
        self.fps_counter = 0
        self.current_fps = 0.0
        print("Statistics reset")
        
    def show_help(self):
        """Display help information"""
        help_text = """
=== Video Display Controls ===
q/ESC : Quit
f     : Toggle fullscreen
s     : Save screenshot
r     : Reset statistics
h     : Show this help
1     : Toggle frame count display
2     : Toggle FPS display
3     : Toggle timestamp display
4     : Toggle resolution display
=============================
        """
        print(help_text)
        
    def get_stats(self):
        """Get current display statistics"""
        runtime = time.time() - self.start_time
        avg_fps = self.frames_displayed / runtime if runtime > 0 else 0
        
        return {
            'frames_displayed': self.frames_displayed,
            'runtime': runtime,
            'current_fps': self.current_fps,
            'average_fps': avg_fps
        }


class MultiWindowDisplay:
    """Display video in multiple windows with different views"""
    
    def __init__(self):
        self.displays = {}
        self.running = False
        
    def add_display(self, name, window_name=None, window_size=(640, 480)):
        """Add a new display window"""
        if window_name is None:
            window_name = f"Video - {name}"
            
        display = VideoDisplay(window_name, window_size)
        self.displays[name] = display
        
        if self.running:
            display.start()
            
        return display
        
    def remove_display(self, name):
        """Remove a display window"""
        if name in self.displays:
            self.displays[name].stop()
            del self.displays[name]
            
    def start_all(self):
        """Start all display windows"""
        self.running = True
        for display in self.displays.values():
            display.start()
            
    def stop_all(self):
        """Stop all display windows"""
        self.running = False
        for display in self.displays.values():
            display.stop()
            
    def update_all(self, frame):
        """Update all displays with the same frame"""
        for display in self.displays.values():
            display.update_frame(frame)
            
    def update_display(self, name, frame):
        """Update a specific display"""
        if name in self.displays:
            self.displays[name].update_frame(frame)
            
    def get_display(self, name):
        """Get a specific display"""
        return self.displays.get(name)


# Example usage and demo
if __name__ == "__main__":
    import sys
    
    def demo_single_window():
        """Demo single window display"""
        print("Single Window Display Demo")
        print("Generating test pattern... Press 'h' for help, 'q' to quit")
        
        display = VideoDisplay("Test Pattern", (800, 600))
        display.start()
        
        # Generate test pattern
        frame_count = 0
        try:
            while True:
                # Create test pattern
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                
                # Moving circle
                center_x = int(320 + 200 * np.sin(frame_count * 0.1))
                center_y = int(240 + 100 * np.cos(frame_count * 0.1))
                cv2.circle(frame, (center_x, center_y), 50, (0, 255, 255), -1)
                
                # Color gradient background
                for y in range(480):
                    for x in range(640):
                        frame[y, x] = [
                            int(255 * x / 640),
                            int(255 * y / 480),
                            int(255 * (frame_count % 100) / 100)
                        ]
                
                display.update_frame(frame)
                frame_count += 1
                
                if not display.running:
                    break
                    
                time.sleep(1/30)  # 30 FPS
                
        except KeyboardInterrupt:
            pass
        finally:
            display.stop()
            
    def demo_multi_window():
        """Demo multiple window display"""
        print("Multi-Window Display Demo")
        print("Press 'q' in any window to quit all")
        
        multi = MultiWindowDisplay()
        
        # Add multiple displays
        main_display = multi.add_display("main", "Main View", (800, 600))
        mini_display = multi.add_display("mini", "Mini View", (320, 240))
        
        # Set quit callback for main display
        def on_key(key):
            if key == ord('q') or key == 27:
                multi.stop_all()
                return True
            return False
            
        main_display.on_key_press = on_key
        mini_display.on_key_press = on_key
        
        multi.start_all()
        
        frame_count = 0
        try:
            while main_display.running and mini_display.running:
                # Create test frame
                frame = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
                
                # Add some pattern
                cv2.rectangle(frame, (50, 50), (590, 430), (255, 255, 255), 2)
                cv2.putText(frame, f"Frame {frame_count}", (60, 100), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                
                multi.update_all(frame)
                frame_count += 1
                
                time.sleep(1/15)  # 15 FPS
                
        except KeyboardInterrupt:
            pass
        finally:
            multi.stop_all()
    
    # Run demo based on command line argument
    if len(sys.argv) > 1 and sys.argv[1] == "multi":
        demo_multi_window()
    else:
        demo_single_window()
