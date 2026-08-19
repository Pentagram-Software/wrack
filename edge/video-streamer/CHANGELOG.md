# Changelog

All notable changes to the Raspberry Pi Camera Streaming Server will be documented in this file.

## [1.2.0] - 2026-05-22 (PEN-56 / M3-1 — WebRTC Pipeline)

### Added
- **`webrtc_streamer.py`** — RTP/SRTP/DTLS streaming pipeline via [aiortc](https://github.com/aiortc/aiortc):
  - `FrameSource` ABC decouples camera hardware from the WebRTC track, enabling
    dependency injection and hardware-free unit testing.
  - `H264VideoStreamTrack` — aiortc `MediaStreamTrack` that paces frames at the
    configured FPS and applies the standard 90 kHz RTP video clock.
  - `WebRTCStreamer` — manages `RTCPeerConnection` lifecycle; embeds DTLS
    certificate fingerprints in SDP answers (RFC 5763/5764 SRTP negotiation is
    handled automatically by aiortc).
  - `WebRTCConfig` — dataclass for STUN server URIs and bitrate bounds.
  - `Picamera2FrameSource` — Pi-hardware-backed `FrameSource` (imported only when
    Picamera2 is available; not used in unit tests).
- **`tests/test_webrtc_streamer.py`** — 50 unit tests covering:
  - `WebRTCConfig` defaults and customisation
  - `H264VideoStreamTrack` PTS/time-base progression and `recv()` contract
  - `WebRTCStreamer` peer connection lifecycle and `close_all()` behaviour
  - SDP offer/answer integration tests verifying `a=fingerprint:` (DTLS) and
    `a=setup:` (SRTP role) attributes in the answer SDP
  - H.264 codec presence in negotiated SDP
- **`pytest.ini`** — enables `asyncio_mode = auto` for pytest-asyncio.
- **`requirements.txt`** — added `aiortc>=1.9.0`, `av>=11.0.0`,
  `pytest-asyncio>=0.23.0`.

## [1.1.0] - 2025-01-XX

### Added
- **Always-chunked UDP protocol** for internet streaming compatibility
- **Frame ID system** for robust frame reassembly
- **NAT-friendly single-socket client model**
- Configurable chunk payload size (default 1200 bytes)
- Automatic client timeout and cleanup (30 seconds)
- Real-time FPS monitoring and status logging
- Comprehensive client example with statistics overlay

### Changed
- **BREAKING**: UDP protocol now always uses chunked transmission
- **BREAKING**: Client must use single socket for registration and receiving
- UDP packets limited to ~1200-byte payloads to avoid IP fragmentation
- Server sends frames to exact client source address for NAT traversal
- Improved error handling and client disconnection detection

### Fixed
- UDP streaming over internet through NAT/routers
- IP fragmentation issues with large UDP packets
- Client connection reliability for remote access

### Protocol Changes
- `FRAME_START` now includes: `[frame_id:u32][frame_size:u32][chunk_count:u32]`
- `CHUNK` now includes: `[frame_id:u32][chunk_index:u32] + payload`
- Removed single-packet `FRAME` format (all frames now chunked)

## [1.0.0] - 2025-01-XX

### Added
- Initial release with three streaming protocols:
  - UDP streaming with basic chunking for large frames
  - TCP streaming with reliable connection handling
  - HTTP/MJPEG streaming for web browser compatibility
- Raspberry Pi Camera v2.1 support via Picamera2
- JPEG compression with configurable quality
- Multi-threaded server architecture
- Client registration and keepalive system
- Basic port forwarding support

### Features
- 640x480 @ 30 FPS video capture
- Real-time frame encoding and transmission
- Multiple concurrent client support
- Cross-platform client compatibility (Python + OpenCV)

---

## Version Schema

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR**: Incompatible API/protocol changes
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible
