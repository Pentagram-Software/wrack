# Project Plan (TPM)

This plan translates the rough timeline into milestones, deliverables,
dependencies, and reporting expectations for the Raspberry Pi Camera Streamer.

## Timeline Overview
- M0: Decisions and Setup (Days 1-2)
- M1: Capture and Encode (Days 3-7)
- M2: HLS Streaming (Days 8-15)
- M3: WebRTC Streaming (Days 16-20)
- M4: Reliability, Config, and Ops (Days 21-24)
- M5: Documentation and Handoff (Days 25-26)

## Milestones and Deliverables

### M0: Decisions and Setup (Days 1-2)
- Confirm encoder path and toolchain (Picamera2 + HW H.264).
- Choose HLS stack (LL-HLS segmenter and HTTP server).
- Choose WebRTC stack (GStreamer `webrtcbin` vs `aiortc`) for follow-on.
- Deliverables:
  - Decision log (stack choices)
  - Environment setup checklist

### M1: Capture and Encode (Days 3-7)
- Implement Picamera2 capture with configurable FPS/resolution.
- Add H.264 encoder config (bitrate/profile/GOP).
- Add logging for FPS/bitrate/encoder status.
- Add unit tests for capture/encode configuration and logging.
- Deliverables:
  - Local Pi pipeline producing H.264 stream
  - Configurable capture/encode settings

### M2: HLS Streaming (Days 8-15)
- Build LL-HLS pipeline on Pi (segmenter + playlist).
- Configure Nginx to serve playlists and segments.
- Validate iOS playback (AVPlayer) and browser playback.
- Validate LAN playback and latency before client integration.
- Validate WAN playback and latency before client integration.
- Create an integration test checklist for HLS playback and latency.
- Deliverables:
  - LL-HLS playback over LAN/WAN
  - Nginx config and HLS output

### M3: WebRTC Streaming (Days 16-20)
- Build WebRTC pipeline on Pi.
- Implement minimal signaling server.
- Create browser client for playback.
- Add reconnect logic and basic health checks.
- Create an integration test checklist for WebRTC playback and reconnect.
- Deliverables:
  - Browser playback over LAN/WAN
  - Signaling service and client demo

### M4: Reliability, Config, and Ops (Days 21-24)
- Add config file + CLI flags.
- Add health endpoint and logging improvements.
- Add basic security (HTTPS/TLS for HLS, WebRTC DTLS/SRTP).
- Enforce unit tests for dev tickets in CI and review checklist.
- Deliverables:
  - MVP-ready operational controls
  - Basic security configuration

### M5: Documentation and Handoff (Days 25-26)
- Update `docs/architecture/ARC42.md` and ADRs.
- Add deployment instructions + usage examples.
- Deliverables:
  - Final docs and release checklist

## Dependencies
- M1 depends on M0 decisions.
- M2 depends on M1 capture/encode pipeline.
- M3 can start after M1, finalize after M2 decisions.
- M4 depends on stable M2 and M3 behavior.
- M5 depends on M4 completion.

## Risks and Mitigations
- HW encoder availability: validate on Pi 5 early (M0).
- HLS latency tuning: use LL-HLS presets and measure end-to-end delay.
- WebRTC complexity: keep signaling minimal; use known GStreamer examples.
- WAN variability: add reconnection logic and log metrics.

## Quality and Review Requirements
- Dev tickets require unit tests for new logic or behavior changes.
- Integration tests are defined and owned by QA for end-to-end playback validation.
- Reviews must verify unit tests exist and pass before approval.

## Status Update Template (TPM)

**Date:** YYYY-MM-DD  
**Milestone:** Mx  
**Status:** On Track / At Risk / Blocked  
**Completed This Period:**
- ...
**Planned Next:**
- ...
**Risks / Issues:**
- ...
**Decisions Needed:**
- ...
