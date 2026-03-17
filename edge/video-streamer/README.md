# Raspberry Pi Camera Video Streaming Server

A high-performance video streaming server for Raspberry Pi 5 with multiple streaming protocols (UDP, TCP, HTTP/MJPEG). Optimized for both local network and internet streaming with NAT traversal support.

## 🚀 Features

- **Multiple Streaming Protocols**:
  - **UDP Streaming**: Low-latency, NAT-friendly chunked transmission
  - **TCP Streaming**: Reliable connection-based streaming
  - **HTTP/MJPEG**: Web browser compatible streaming

- **Internet-Ready UDP Protocol**:
  - Always-chunked transmission (1200-byte payloads) to avoid IP fragmentation
  - NAT-friendly single-socket client model
  - Frame IDs for robust reassembly
  - Automatic client timeout and cleanup

- **Camera Features**:
  - Raspberry Pi Camera v2.1 support via Picamera2
  - 640x480 @ 30 FPS (configurable)
  - JPEG compression with adjustable quality
  - Real-time frame rate monitoring

## 📋 Requirements

### Hardware
- Raspberry Pi 5 (tested)
- Raspberry Pi Camera v2.1 or compatible
- Network connection

### Software
- Python 3.x
- See `requirements.txt` for Python dependencies

## 🛠️ Installation

1. **Clone the repository**:
```bash
git clone https://github.com/yourusername/rpi-camera-streaming.git
cd rpi-camera-streaming
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Enable camera interface**:
```bash
sudo raspi-config
# Navigate to Interface Options > Camera > Enable
```

## 🎯 Quick Start

### Server (Raspberry Pi)

Run the streaming server (uses `config/config.json` by default):
```bash
python3 streamer.py
```

Choose your streaming method:
- **1**: UDP Streaming (recommended for internet)
- **2**: TCP Streaming (reliable, local network)
- **3**: HTTP/MJPEG (web browser compatible)

### Configure Capture Settings

You can configure capture and encoder settings using either JSON config or CLI flags.

#### Default JSON config
Edit `config/config.json`:
```json
{
  "width": 1280,
  "height": 720,
  "fps": 30,
  "bitrate": 2000000,
  "gop": 30,
  "profile": "baseline"
}
```

#### Use a custom JSON file
```bash
python3 streamer.py --config /path/to/config.json
```

#### Override via CLI (highest priority)
```bash
python3 streamer.py --width 1920 --height 1080 --fps 25 --bitrate 3000000 --gop 60 --profile main
```

#### Priority order
1. CLI flags
2. JSON config (if present)
3. Defaults (640x480 @ 30 FPS)

#### Argument reference
- `--width`: Video width in pixels (default: 640)
- `--height`: Video height in pixels (default: 480)
- `--fps`: Frames per second (default: 30)
- `--bitrate`: H.264 target bitrate in bits/sec (default: 2_000_000)
- `--gop`: H.264 GOP / keyframe interval in frames (default: 30)
- `--profile`: H.264 profile (`baseline`, `main`, `high`) (default: `baseline`)

### Client Examples

#### UDP Client (Python)
```python
import socket
import struct
import pickle
import cv2

# Single socket for NAT-friendly operation
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(b"REGISTER_CLIENT", ("server_ip", 9999))

pending = {}
expected = {}

while True:
    data, addr = sock.recvfrom(65507)
    
    if data == b"REGISTERED":
        print("Connected to server!")
        continue
    
    if data.startswith(b"FRAME_START"):
        frame_id, frame_size, chunk_count = struct.unpack("LLL", data[11:23])
        pending[frame_id] = bytearray(frame_size)
        expected[frame_id] = chunk_count
        
    elif data.startswith(b"CHUNK"):
        frame_id, chunk_index = struct.unpack("LL", data[5:13])
        payload = data[13:]
        
        if frame_id in pending:
            offset = chunk_index * 1200
            pending[frame_id][offset:offset+len(payload)] = payload
            expected[frame_id] -= 1
            
            if expected[frame_id] == 0:
                # Frame complete - decode and display
                frame_data = bytes(pending.pop(frame_id))
                expected.pop(frame_id, None)
                
                jpeg_buffer = pickle.loads(frame_data)
                frame = cv2.imdecode(jpeg_buffer, cv2.IMREAD_COLOR)
                cv2.imshow('Stream', frame)
                
                if cv2.waitKey(1) == 27:  # ESC to exit
                    break

cv2.destroyAllWindows()
```

#### Web Browser (HTTP)
Simply navigate to: `http://raspberry_pi_ip:8080`

## 🌐 Network Configuration

### For Internet Streaming (UDP)

1. **Port Forward UDP 9999** on your router to the Raspberry Pi
2. **Firewall**: Allow UDP 9999 inbound on Raspberry Pi
3. **Client**: Use single UDP socket (see example above)

### Protocol Comparison

| Protocol | Latency | Reliability | NAT Support | Browser Support |
|----------|---------|-------------|-------------|-----------------|
| UDP      | Lowest  | Medium      | ✅ Yes      | ❌ No          |
| TCP      | Medium  | Highest     | ✅ Yes      | ❌ No          |
| HTTP     | Highest | High        | ✅ Yes      | ✅ Yes         |

## 📊 Performance

- **Resolution**: 640x480 pixels
- **Frame Rate**: Up to 40+ FPS (network dependent)
- **Bandwidth**: ~600KB - 2.4MB/s (depends on scene complexity)
- **Latency**: <100ms (UDP), ~200-500ms (TCP/HTTP)

## 🔧 Configuration

### Camera Settings
Use `config/config.json` or CLI flags (`--width`, `--height`, `--fps`). The default config file is loaded automatically unless overridden with `--config`.

### JPEG Quality
Adjust compression quality (1-100):
```python
cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
```

### Logs
Encoder settings are written to `logs/streamer.log` with timestamps at startup.

### UDP Chunk Size
Modify chunk payload size:
```python
self.chunk_payload_size = 1200  # bytes
```

## 📖 Protocol Documentation

See [`UDP_Frame_Format_Documentation.md`](UDP_Frame_Format_Documentation.md) for detailed protocol specifications.

## 🐛 Troubleshooting

### UDP Frames Not Received Over Internet
- **Cause**: IP fragmentation or NAT issues
- **Solution**: Use the updated always-chunked protocol (v1.1+)

### Client Can't Connect
- **Check**: Port forwarding (UDP 9999)
- **Check**: Firewall settings
- **Check**: Client uses same socket for registration and receiving

### Low Frame Rate
- **Reduce JPEG quality**: Lower from 80 to 50-60
- **Check network bandwidth**: Monitor with `iftop` or similar
- **Optimize scene**: Reduce motion/complexity in camera view

## ✅ Testing

### Option A: Virtual Environment (recommended on Raspberry Pi)
```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-full

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pytest -q
```

### Option B: System package
```bash
sudo apt-get update
sudo apt-get install -y python3-pytest
pytest -q
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Picamera2](https://github.com/raspberrypi/picamera2) for Raspberry Pi camera interface
- Uses OpenCV for image processing and encoding
- Inspired by the need for robust internet video streaming from Raspberry Pi

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/rpi-camera-streaming/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/rpi-camera-streaming/discussions)

---

**Made with ❤️ for the Raspberry Pi community**
