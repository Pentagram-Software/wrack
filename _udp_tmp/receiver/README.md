# UDP Video Receiver Client

A lightweight UDP video receiver that runs on a local laptop to test streaming
from a Raspberry Pi. The client supports chunked UDP frame reassembly and two
payload modes:

- `jpeg` (legacy pickle + JPEG payloads)
- `h264` (H.264 payload bytes decoded with PyAV)

## Features

- ✅ **UDP Video Streaming**: Fast, low-latency video reception
- ✅ **Chunked Frame Support**: Handles large frames split into 1200-byte chunks to avoid IP fragmentation
- ✅ **NAT-Friendly**: Single-socket architecture works through home routers
- ✅ **Frame Reassembly**: Robust frame reconstruction with duplicate detection
- ✅ **Real-time Statistics**: FPS monitoring and frame counting
- ✅ **Cross-Platform**: Works on macOS, Linux, and Windows
- ✅ **OpenCV Integration**: Direct video display with frame overlays
- ✅ **Internet Ready**: Designed for streaming over WAN connections

## Performance

- **Frame Rate**: 25-30 FPS typical performance
- **Latency**: Low latency UDP transmission
- **Reliability**: Handles packet loss gracefully
- **Bandwidth**: ~600KB-2.4MB per second (depends on video quality)

## Requirements

```bash
pip install opencv-python numpy
```

Optional (needed when running with `--stream-format h264`):

```bash
pip install av
```

If PyAV installation fails on macOS, install FFmpeg first:

```bash
brew install ffmpeg
```

## Quick Start

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/udp-video-receiver.git
   cd udp-video-receiver
   ```
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the client**:
   ```bash
   python3 main.py
   ```

4. **Default behavior**:
   - Reads `config/config.json` if present
   - Uses config values unless CLI flags override them
   - Falls back to interactive prompts when required values are missing

## Configuration File

Default config path:

```bash
receiver/config/config.json
```

Example:

```json
{
  "mode": "client_server",
  "stream_format": "jpeg",
  "server_ip": "192.168.1.216",
  "server_port": 9999,
  "client_port": 9999,
  "listen_port": 9999
}
```

Precedence order:

1. CLI args
2. Config file
3. Built-in defaults

## Usage Examples

### Local Network Connection (default JPEG mode)
```bash
python3 main.py --mode client_server --stream-format jpeg --server-ip 192.168.1.216
```

### H.264 Mode
```bash
python3 main.py --mode client_server --stream-format h264 --server-ip 192.168.1.216
```

### Broadcast Mode
```bash
python3 main.py --mode broadcast --listen-port 9999
```

### Use a custom config file
```bash
python3 main.py --config /path/to/receiver-config.json
```

### Internet Connection
```bash
python3 main.py --mode client_server --server-ip 178.183.200.201 --server-port 9999
```

## Network Configuration

### For Internet Streaming

**Server Side (Raspberry Pi)**:
- Forward UDP port 9999 on your router to the Raspberry Pi

**Client Side (Your Computer)**:
- Forward UDP port 9999 on your router to your computer's local IP
- Allow Python through your firewall for UDP connections

### Port Forwarding Setup

1. **Find your local IP**:
   ```bash
   # macOS/Linux
   ifconfig | grep inet
   
   # Windows  
   ipconfig
   ```

2. **Router Configuration**:
   - Protocol: UDP
   - External Port: 9999
   - Internal IP: [Your computer's local IP]
   - Internal Port: 9999

## Protocol Details

The client implements UDP Video Streaming Protocol v1.1:

### Frame Format
- **FRAME_START**: `b"FRAME_START" + [frame_id:u32][frame_size:u32][chunk_count:u32]`
- **CHUNK**: `b"CHUNK" + [frame_id:u32][chunk_index:u32] + payload (≤1200 bytes)`

### Connection Flow
1. Client sends `REGISTER_CLIENT` to server:9999
2. Server responds with `REGISTERED`
3. Server streams chunked video frames
4. Client reassembles and displays frames
5. Periodic `KEEPALIVE` messages maintain connection

## Video Display Features

- **Frame Counter**: Shows total frames received
- **Real-time Statistics**: Updates every 5 seconds
- **Quality Overlay**: Frame count displayed on video
- **Keyboard Controls**: Press 'q' to quit

## File Structure

```
udp-video-receiver/
├── main.py                           # Main UDP client application
├── simple_display.py                 # Enhanced video display module
├── video_display.py                  # Advanced threading display module
├── enhanced_client.py                # Feature-rich client implementation
├── display_example.py                # Display module usage examples
├── upnp_helper.py                    # UPnP port forwarding helper
├── UDP_Frame_Format_Documentation.md # Protocol specification
├── README_Display.md                 # Display module documentation
├── requirements.txt                  # Python dependencies
└── README.md                         # This file
```

## Advanced Usage

### Using Enhanced Display Module

```python
from simple_display import SimpleDisplay

# Create display with custom settings
display = SimpleDisplay(
    window_name="My Video Stream",
    show_fps=True,
    show_timestamp=True
)

# In your frame processing loop
display.show_frame(frame)
```

### Custom Statistics

The client tracks comprehensive statistics:
- Total frames received
- Average FPS over session
- Runtime duration
- Real-time performance metrics

## Troubleshooting

### No Video Frames Received

1. **Check network connectivity**:
   ```bash
   ping [server-ip]
   ```

2. **Verify port forwarding**:
   - Ensure UDP 9999 is forwarded on both sides
   - Check firewall settings

3. **Test local connection first**:
   - Try connecting on the same network (192.168.x.x)
   - If local works but internet doesn't, it's a network configuration issue

4. **Check payload mode mismatch**:
   - If receiver uses `--stream-format h264` but streamer sends pickled JPEG
     payloads, frames will not decode.
   - Ensure sender and receiver use the same payload mode.

### Low Frame Rate

- **Network bandwidth**: Ensure sufficient upload/download speed
- **Packet loss**: Check for network congestion
- **Processing power**: Verify client machine can handle video decoding

### Connection Timeouts

- **Firewall blocking**: Allow Python/UDP through firewall
- **Router NAT**: Ensure port forwarding is configured correctly
- **Keep-alive**: Client sends periodic keep-alive messages

### PyAV / H.264 Decode Issues

- **PyAV missing**:
  ```bash
  pip install av
  ```
- **PyAV install fails on macOS**:
  ```bash
  brew install ffmpeg
  pip install av
  ```
- **No decoded frames in H.264 mode**:
  - Verify streamer is actually sending H.264 payload bytes (not pickle/JPEG).
  - Confirm receiver is started with `--stream-format h264`.
  - Check runtime logs for decode failures counter.

## Development

### Protocol Compatibility

The client supports multiple struct formats for cross-platform compatibility:
- 64-bit L format (Raspberry Pi)
- 32-bit I format (other platforms)
- Automatic format detection

### Adding Features

The modular design allows easy extension:
- Custom payload routing in `process_frame_data()`
- JPEG decode path in `process_pickled_frame()`
- H.264 decode path in `process_h264_frame()`
- Enhanced statistics in `display_stats()`

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- OpenCV for video processing capabilities
- Raspberry Pi Foundation for the excellent Pi Camera ecosystem
- Python community for robust networking libraries

## Related Projects

- **UDP Video Server**: Compatible Raspberry Pi server implementation
- **TCP Video Client**: Reliable alternative for local networks
- **HTTP Streaming**: Web browser compatible streaming solution

---

**Performance**: Tested at 25-30 FPS over both local networks and internet connections  
**Compatibility**: Python 3.7+, OpenCV 4.x, Cross-platform  
**Status**: Production ready ✅
