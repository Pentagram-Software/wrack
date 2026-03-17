# Enhanced Video Display Capabilities

This directory now contains enhanced video display capabilities for the UDP video streaming client.

## Files Overview

### Core Files
- **`main.py`** - Original UDP video client with basic display
- **`UDP_Frame_Format_Documentation.md`** - Protocol documentation

### Enhanced Display Files
- **`simple_display.py`** - ✅ **RECOMMENDED** - Simple enhanced display with overlay features
- **`video_display.py`** - Advanced display with threading (may have compatibility issues)
- **`enhanced_client.py`** - Full-featured client with multi-window support
- **`display_example.py`** - Example of integrating display modules

## Quick Start - Enhanced Display

### Option 1: Simple Enhanced Display (Recommended)
```bash
python3 simple_display.py
```

**Features:**
- ✅ Real-time FPS counter
- ✅ Frame counter overlay
- ✅ Timestamp display
- ✅ Resolution information
- ✅ Runtime counter
- ✅ Fullscreen toggle
- ✅ Statistics display
- ✅ Interactive controls

### Option 2: Original Basic Display
```bash
python3 main.py
```

**Features:**
- ✅ Basic video display
- ✅ Periodic statistics (every 5 seconds)
- ✅ Frame counter overlay

## Enhanced Display Controls

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `q` / `ESC` | Quit application |
| `f` | Toggle fullscreen mode |
| `h` | Show help message |
| `p` | Print current statistics |
| `r` | Reset statistics |
| `1` | Toggle frame count display |
| `2` | Toggle FPS display |
| `3` | Toggle timestamp display |
| `4` | Toggle resolution display |
| `5` | Toggle runtime display |

### Display Features

#### Real-time Overlays
- **Frame Count**: Shows total frames received
- **FPS**: Current frames per second
- **Timestamp**: Current time (HH:MM:SS)
- **Resolution**: Video dimensions (e.g., 640x480)
- **Runtime**: Total streaming time

#### Statistics
- **Real-time FPS calculation** (updated every second)
- **Average FPS** over entire session
- **Total frame count**
- **Session runtime**

## Usage Examples

### Basic Enhanced Streaming
```bash
# Start enhanced client
python3 simple_display.py

# Enter server details
Enter server IP: 192.168.1.216
Enter server port (default 9999): 
Enter client port (default auto-assign): 

# Video window will open with overlays
# Press 'h' in video window for help
```

### Performance Monitoring
The enhanced display shows real-time performance metrics:

```
Frames: 1234        # Top-left corner
FPS: 27.1           # Real-time FPS
Resolution: 640x480 # Video dimensions
Time: 14:30:25      # Current time
                    Runtime: 45.2s  # Top-right corner
```

### Statistics Output
Press `p` in the video window to see detailed stats:

```
=== Display Statistics ===
Frames displayed: 1234
Runtime: 45.2s
Current FPS: 27.1
Average FPS: 27.3
========================
```

## Technical Details

### Simple Display Architecture
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   UDP Client    │───►│  Simple Display  │───►│   CV2 Window    │
│                 │    │                  │    │                 │
│ - Receives data │    │ - Adds overlays  │    │ - Shows video   │
│ - Decodes JPEG  │    │ - Calculates FPS │    │ - Handles keys  │
│ - Manages stats │    │ - Handles input  │    │ - Fullscreen    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Performance
- **✅ 26-27 FPS** consistent performance
- **✅ Low latency** - direct frame display
- **✅ Minimal overhead** - simple overlay rendering
- **✅ Stable operation** - no threading complications

### Compatibility
- **✅ macOS** - Tested and working
- **✅ OpenCV 4.x** - Compatible with modern OpenCV
- **✅ Python 3.x** - Standard Python compatibility

## Troubleshooting

### Common Issues

#### 1. OpenCV Window Issues
```python
# If you see "Unknown C++ exception from OpenCV"
# Use simple_display.py instead of video_display.py
python3 simple_display.py
```

#### 2. No Video Display
```bash
# Check if server is running and accessible
ping 192.168.1.216

# Verify port is correct (default 9999)
# Check firewall settings
```

#### 3. Low FPS Performance
- **Expected**: 26-27 FPS
- **If lower**: Check network connection
- **If choppy**: Try fullscreen mode (press `f`)

### Debug Information
The simple display shows minimal debug output:
```
Simple Enhanced UDP Video Client
Features: FPS display, frame counter, timestamp, resolution, runtime
Press 'h' in video window for help

Client bound to port 54321
Requesting stream from 192.168.1.216:9999
Successfully registered with server
Receiving video stream... Press 'q' to quit
```

## Integration Guide

### Adding Enhanced Display to Your Code

```python
from simple_display import SimpleVideoDisplay

class YourUDPClient:
    def __init__(self):
        self.display = SimpleVideoDisplay("Your Stream", (1024, 768))
        
    def process_frame(self, frame):
        # Your frame processing here
        
        # Display with enhancements
        should_quit = self.display.display_frame(frame)
        if should_quit:
            self.running = False
            
    def cleanup(self):
        self.display.cleanup()
```

## Future Enhancements

### Planned Features
- ✅ Screenshot capability
- 🔄 Multiple window support
- 🔄 Recording capability
- 🔄 Zoom and pan controls
- 🔄 Frame rate adjustment

### Advanced Features (video_display.py)
- Multi-threaded display
- Multiple window support
- Advanced statistics visualization
- Custom key handlers

---

## Summary

The enhanced display system provides a professional video streaming experience with:

1. **Real-time performance monitoring**
2. **Interactive controls**
3. **Professional overlays**
4. **Stable, high-performance operation**

**Recommended**: Use `simple_display.py` for the best balance of features and stability.

---

*Last updated: January 2025*
