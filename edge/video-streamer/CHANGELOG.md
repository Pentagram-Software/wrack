# Changelog

All notable changes to the Raspberry Pi Camera Streaming Server will be documented in this file.

## [1.2.0] - 2026-01-XX

### Added
- **Health endpoint** (`GET /health`): returns a JSON snapshot of streaming health on a
  dedicated HTTP server (default port 9000, configurable via `--health-port` or `health_port`
  in `config.json`).  Available for all transport modes (UDP, TCP, HTTP).  HTTP mode also
  exposes `/health` on its own port 8080 for convenience.
- **`health.py`** module: `StreamStats` (thread-safe metrics dataclass), `HealthServer`
  (lightweight daemon-threaded HTTP server), and `configure_logging()` extracted here.
  No hardware dependencies — fully unit-testable without a real Raspberry Pi camera.
- **`StreamStats`**: tracks `transport`, `streaming_active`, `camera_ready`,
  `frames_sent`, `clients_connected`, `errors`, rolling FPS (5-second window),
  and process uptime.  Updated live by all three streamers.
- **Structured logging**: `configure_logging()` now supports an optional console
  (`StreamHandler`) in addition to the file handler, a configurable log level, and a
  richer format string (`asctime levelname name message`).
- `--health-port` CLI flag and `health_port` JSON config key (default 9000, validated
  in range 1–65535).
- 40 new unit tests across `tests/test_health.py` and `tests/test_logging.py` covering
  `StreamStats` defaults, `record_frame()`, `to_dict()`, `HealthServer` HTTP responses,
  lifecycle (start/stop/double-stop), and all `configure_logging()` branches.
- 5 new `test_config.py` tests covering `health_port` default, JSON, CLI, override, and
  validation.

### Changed
- All `print()` calls inside streaming classes replaced with `LOGGER.info()`,
  `LOGGER.warning()`, and `LOGGER.error()` for consistent structured log output.
- `streamer.py` imports `StreamStats`, `HealthServer`, and `configure_logging` from the
  new `health.py` module instead of defining its own `configure_logging`.
- `VideoStreamer.__init__()` accepts an optional `stats: StreamStats` parameter so the
  caller can inject a shared stats object (used in `__main__` to bridge the streamer and
  `HealthServer`).
- `StreamConfig` gains `health_port: int = 9000` field.
- `config/config.json` includes `"health_port": 9000`.

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
