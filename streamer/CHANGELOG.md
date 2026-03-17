# Changelog

All notable changes to the Raspberry Pi Camera Streaming Server will be documented in this file.

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
