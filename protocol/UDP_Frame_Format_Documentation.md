# UDP Video Streaming Frame Format Documentation

## Overview

This document describes the frame format and data structure used in the
Raspberry Pi UDP video streaming system. The transport packet structure is the
same for all modes (`FRAME_START` + `CHUNK`), while frame payload encoding can
be either legacy JPEG/pickle or H.264 (AVC) bitstream bytes.

## Frame Processing Pipeline

### Legacy JPEG/Pickle Mode

```
Raw Camera Frame (640x480 RGB888)
    ↓ Color Conversion
BGR Frame 
    ↓ JPEG Compression (80% quality)
JPEG Buffer (bytes)
    ↓ Python Pickle Serialization
Pickled JPEG Data
    ↓ UDP Packetization with Headers
Network Packets → Client
```

### H.264 Mode

```
Raw Camera Frame (RGB888)
    ↓ H.264 Encoding
H.264 Bitstream Frame (bytes)
    ↓ UDP Packetization with Headers
Network Packets → Client
    ↓ H.264 Decode (PyAV/FFmpeg)
BGR Frame
```

## Payload Encoding Modes

### 1) JPEG + Pickle (legacy compatibility)
- Compress frame with JPEG (`cv2.imencode`).
- Serialize JPEG bytes with Python `pickle`.
- Reassemble chunks on client, then deserialize and decode JPEG.

### 2) H.264 (new option)
- Encode frame with H.264/AVC.
- Send encoded frame bytes directly as chunk payload (no pickle layer).
- Reassemble chunks on client, then decode H.264 payload.

## Compression Details

### Image Compression
- **Format**: JPEG compression using OpenCV
- **Quality**: 80% JPEG quality (`cv2.IMWRITE_JPEG_QUALITY, 80`)
- **Method**: `cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])`
- **Type**: Lossy compression with good size/quality balance
- **Independence**: Each frame is compressed independently (no inter-frame compression)

### Serialization
- **Method**: Python pickle serialization
- **Function**: `pickle.dumps(jpeg_buffer)`
- **Purpose**: Converts JPEG byte buffer into transmittable binary format
- **Requirement**: Clients must be Python-based to deserialize

### H.264 Encoding (alternative mode)
- **Codec**: H.264/AVC
- **Payload**: Encoded bitstream bytes (no pickle serialization)
- **Decode**: Client decodes with H.264-capable decoder (e.g., PyAV)

## UDP Packet Structure (Always-Chunked, NAT-Friendly)

To avoid IP fragmentation across the internet, frames are always sent as small
UDP chunks (default payload ~1200 bytes). Each frame has a unique `frame_id`.
This packet format is shared by both JPEG and H.264 payload modes.

### Frame Start Packet
```
┌──────────────┬────────────────────┬──────────────────┬──────────────────┐
│ "FRAME_START"│ frame_id (uint32)  │ frame_size (u32) │ chunk_count (u32)│
│ 11 bytes     │ 4 bytes            │ 4 bytes          │ 4 bytes          │
└──────────────┴────────────────────┴──────────────────┴──────────────────┘
```

### Chunk Packets
```
┌─────────┬────────────────────┬────────────────────┬────────────────────┐
│ "CHUNK" │ frame_id (uint32)  │ chunk_index (u32)  │ chunk_payload (<=1200B)
│ 5 bytes │ 4 bytes            │ 4 bytes            │ variable           │
└─────────┴────────────────────┴────────────────────┴────────────────────┘
```

### Chunk Payload Semantics by Mode
- **JPEG mode**: payload bytes are part of a pickled JPEG buffer.
- **H.264 mode**: payload bytes are part of an H.264 bitstream frame.

### Implementation (Sender)
```python
payload_size = 1200
chunk_count = (size + payload_size - 1) // payload_size
sock.sendto(b"FRAME_START" + struct.pack("LLL", frame_id, size, chunk_count), addr)

for idx, off in enumerate(range(0, size, payload_size)):
    chunk = data[off:off+payload_size]
    sock.sendto(b"CHUNK" + struct.pack("LL", frame_id, idx) + chunk, addr)
```

## Network Protocol

### Client Registration (Single Port, NAT-Friendly)
Clients must register before receiving frames:

```
Client → Server (UDP 9999): "REGISTER_CLIENT" (from a single UDP socket)
Server → Client: "REGISTERED"
```

- **Single socket model**: Client uses the SAME UDP socket to send `REGISTER_CLIENT` and to `recvfrom()` frames. This preserves NAT mappings.
- **Port**: Server listens on UDP 9999. Frames are sent back to the exact source address (IP:port) used by the registration packet.
- **Keepalive**: Client sends `KEEPALIVE` every ~15–20 seconds to keep NAT mapping alive.
- **Disconnect**: Client may send `DISCONNECT` when done.

### Server Configuration
- **Listening Port**: 9999 (UDP)
- **Binding**: `0.0.0.0:9999` (all interfaces)
- **Max Packet Size**: 65,507 bytes (UDP maximum)
- **Client Timeout**: 30 seconds

## Frame Specifications

### Camera Settings
- **Resolution**: 640x480 pixels
- **Format**: RGB888 → BGR (OpenCV standard)
- **Frame Rate**: 30 FPS (configurable)
- **Color Space**: sRGB

### Size Characteristics
- **Typical Frame Size**: 15-50 KB (depends on scene complexity)
- **Maximum Frame Size**: ~921 KB (640×480×3 uncompressed)
- **Compressed Size**: ~20-80 KB with JPEG 80% quality
- **Variable Size**: Frame size varies based on image complexity

## Performance Metrics

### Observed Performance
- **Target FPS**: 30
- **Actual FPS**: 13.6-40.7 (varies with network conditions)
- **Throughput**: ~273 frames per 10 seconds average
- **Latency**: Low (UDP + minimal processing)

### Bandwidth Usage
- **Per Frame**: ~20-80 KB
- **Per Second**: ~600 KB - 2.4 MB (at 30 FPS)
- **Per Minute**: ~36-144 MB

## Client Implementation Guide

### Basic Client Structure (Single Socket, JPEG Mode)
```python
import socket
import pickle
import cv2
import struct

# One UDP socket for both register and receive
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Register (let OS choose source port; NAT will map it)
sock.sendto(b"REGISTER_CLIENT", (server_ip, 9999))

# State for assembling frames
pending = {}
expected = {}

while True:
    data, addr = sock.recvfrom(65507)

    if data == b"REGISTERED":
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
                frame_data = bytes(pending.pop(frame_id))
                expected.pop(frame_id, None)
                # Deserialize and display
                jpeg_buffer = pickle.loads(frame_data)
                frame = cv2.imdecode(jpeg_buffer, cv2.IMREAD_COLOR)
                cv2.imshow('Stream', frame)
                if cv2.waitKey(1) == 27:
                    break
```

### H.264 Client Notes

After reassembly, use an H.264 decoder instead of `pickle.loads(...)`:

```python
# frame_data is reassembled bytes for one frame_id
import av

codec = av.CodecContext.create("h264", "r")
packets = codec.parse(frame_data)
decoded = []
for p in packets:
    decoded.extend(codec.decode(p))

if decoded:
    frame = decoded[-1].to_ndarray(format="bgr24")
    cv2.imshow("Stream", frame)
```

The UDP framing (`FRAME_START` / `CHUNK`) remains unchanged.

### Chunk Reassembly
Clients must:
1. Receive `FRAME_START` (frame_id, frame_size, chunk_count)
2. Collect all `CHUNK` packets for that frame_id
3. Place each chunk by `offset = chunk_index * payload_size` (default 1200)
4. When all chunks arrive, concatenate buffer and deserialize

## Advantages & Limitations

### Advantages
- ✅ **Internet-safe UDP**: No reliance on IP fragmentation
- ✅ **NAT-friendly**: Single-socket client model works through typical home routers
- ✅ **Low Latency**: Small UDP packets; immediate decode upon full frame
- ✅ **Supports migration**: Same UDP framing for JPEG and H.264 payload modes

### Limitations
- ❌ **No FEC/Resend**: Lost chunks drop a frame
- ❌ **JPEG mode only**: Python/pickle deserialization requirement
- ❌ **JPEG mode only**: Pickle deserialization has security implications
- ❌ **H.264 mode**: Decoder keyframe/warm-up behavior may drop initial frames
- ❌ **No Synchronization**: No frame timing or sync mechanisms

## Alternative Considerations

For production systems, consider:
- **H.264 Encoding**: Better compression ratios
- **WebRTC**: Standard video streaming protocol
- **Raw Binary**: Remove pickle dependency
- **TCP Fallback**: For reliability-critical applications
- **Frame Buffering**: For smoother playback

---

**Document Version**: 1.2  
**Last Updated**: March 2026  
**System**: Raspberry Pi 5 + Pi Camera v2.1  
**Software**: Python 3.x, OpenCV, Picamera2
