# HLS and LL-HLS Overview

This document summarizes how HLS (HTTP Live Streaming) and LL-HLS are expected
to work in this project, including packaging, encoding, and serving.

## 1. What We Use and Why
- **Protocol**: HLS with Low-Latency HLS (LL-HLS) extensions.
- **Goal**: iOS-native playback (AVPlayer) with low latency.
- **Transport**: HTTP(S) via Nginx serving playlists and segments.

## 2. Media Pipeline (High-Level)
1. Capture frames from Pi Camera via Picamera2.
2. Encode to H.264 (hardware accelerated if available).
3. Package into LL-HLS playlists and segments (fMP4).
4. Serve `.m3u8` playlists and `.m4s` segments via Nginx.

## 3. Encoding Guidance
- **Codec**: H.264/AVC (baseline or main).
- **GOP/keyframe interval**: ~1s to align with low-latency segments.
- **Bitrate**: Configurable; start with a fixed bitrate for predictability.
- **Audio**: Optional; if added, AAC at a low bitrate.

## 4. LL-HLS Packaging
- **Segments**: ~1s target duration.
- **Parts**: 200–500 ms parts for low-latency fetch.
- **Playlist**: Live playlist with partial segment metadata.
- **Container**: fMP4 fragments (`.m4s`) for LL-HLS.

## 5. Delivery and Caching
- **HTTP server**: Nginx (start with HTTP on LAN).
- **MIME types**:
  - `.m3u8` → `application/vnd.apple.mpegurl`
  - `.m4s` → `video/mp4`
- **Caching**: Short/no-cache for playlists; short max-age for segments.

## 6. Latency Targets
- **LL-HLS**: 2–4 seconds end-to-end (LAN), tunable via segment/part size.
- **WebRTC** (future): < 500 ms end-to-end.

## 7. Testing Checklist (HLS)
- Validate playlist updates frequently (no stale playlists).
- Confirm segments are written and served continuously.
- Test iOS playback in Safari or AVPlayer app.
- Measure end-to-end latency on LAN and WAN.

## 8. Open Items
- Finalize segment and part durations after initial measurements.
- Decide whether HTTPS is required for the first WAN test.
