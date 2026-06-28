# HLS Integration Test Checklist

**Milestone**: M2-6 HLS Integration Checklist
**Related tickets**: M2-1 through M2-5 (pipeline, Nginx, iOS/web playback, LAN/WAN validation)
**Runbook**: See [HLS_RUNBOOK.md](./HLS_RUNBOOK.md) for operating procedures.

## Overview

This checklist validates end-to-end HLS playback from the Raspberry Pi camera pipeline through Nginx to iOS (AVPlayer/Safari) and web (hls.js) clients. Run this checklist after each significant change to the HLS pipeline and as a gate before any production deployment.

---

## Prerequisites

Before running any test phase, confirm the following:

- [ ] Raspberry Pi 5 powered on and reachable over the test network
- [ ] Pi Camera v2.1 physically connected and recognised (`vcgencmd get_camera` shows `detected=1`)
- [ ] Picamera2 installed and the capture process can start without errors
- [ ] H.264 encoder configuration file present (`edge/video-streamer/config/config.json`)
- [ ] HLS segmenter/packager process (FFmpeg or Picamera2 LL-HLS output) is configured
- [ ] Nginx installed and configured; test config with `nginx -t`
- [ ] HLS output directory is writable by the streaming process and readable by Nginx
- [ ] A LAN client device is available for playback testing (iOS device and/or desktop browser)
- [ ] Network conditions noted (SSID, signal strength, measured LAN bandwidth)
- [ ] `ffprobe` available on a test machine for playlist/segment inspection

---

## Phase 1 — Pipeline Component Tests

### 1.1 Capture and Encoder

| # | Test | Expected Result | Pass | Notes |
|---|------|-----------------|------|-------|
| 1.1.1 | Start the capture process; confirm it launches without errors | No exception in startup log | | |
| 1.1.2 | Inspect logs for reported FPS; compare against configured value | Reported FPS ≥ 90% of configured FPS (e.g. ≥ 27 FPS for 30 FPS config) | | |
| 1.1.3 | Inspect logs for reported bitrate; compare against configured value | Reported bitrate within ±20% of target | | |
| 1.1.4 | Check encoder profile reported in log matches `config.json` value | Profile matches (`baseline` / `main` / `high`) | | |
| 1.1.5 | Run for 60 seconds; confirm no encoder crash or restart logged | Zero encoder restart events | | |
| 1.1.6 | Verify CPU usage on Pi with `top`/`htop` | CPU usage < 50% sustained over 30 s | | |

### 1.2 HLS Segmenter / Packager

| # | Test | Expected Result | Pass | Notes |
|---|------|-----------------|------|-------|
| 1.2.1 | Confirm HLS output directory contains a playlist file | `playlist.m3u8` (or configured name) present within 5 s of process start | | |
| 1.2.2 | Confirm `.m4s` (fMP4) segment files are created | New `.m4s` files appear in output directory each second | | |
| 1.2.3 | Confirm `.m3u8` playlist is updated at least every 2 s | Playlist `Last-Modified` header advances at each poll | | |
| 1.2.4 | Inspect playlist with `ffprobe -v quiet -print_format json -show_entries format_tags playlist.m3u8` | No ffprobe errors; `EXT-X-TARGETDURATION` present and ≤ 2 | | |
| 1.2.5 | Confirm `EXT-X-PART` tags present in playlist (LL-HLS) | `EXT-X-PART-INF` and `EXT-X-PART` entries visible in playlist text | | |
| 1.2.6 | Confirm `EXT-X-SERVER-CONTROL` with `CAN-BLOCK-RELOAD=YES` present | Tag present in playlist for blocking playlist reload support | | |
| 1.2.7 | Check keyframe/GOP interval aligns with segment boundary | `ffprobe` on a segment shows keyframe at or near segment start | | |

### 1.3 Nginx HTTP Server

| # | Test | Expected Result | Pass | Notes |
|---|------|-----------------|------|-------|
| 1.3.1 | `curl -I http://<pi-ip>/hls/playlist.m3u8` returns HTTP 200 | Status `200 OK` | | |
| 1.3.2 | `Content-Type` header for `.m3u8` is correct | `application/vnd.apple.mpegurl` or `application/x-mpegurl` | | |
| 1.3.3 | `curl -I http://<pi-ip>/hls/<segment>.m4s` returns HTTP 200 | Status `200 OK` | | |
| 1.3.4 | `Content-Type` header for `.m4s` is correct | `video/mp4` | | |
| 1.3.5 | Cache-Control for playlist is set to prevent stale responses | `Cache-Control: no-cache` or `max-age=0` for `.m3u8` | | |
| 1.3.6 | Cache-Control for segments allows short caching | `max-age ≤ 10` for `.m4s` files | | |
| 1.3.7 | CORS headers present if serving to a different origin web client | `Access-Control-Allow-Origin` header present | | |
| 1.3.8 | Nginx access log records requests without errors | No `5xx` entries in `/var/log/nginx/access.log` during test | | |

---

## Phase 2 — Playlist and Segment Integrity

| # | Test | Expected Result | Pass | Notes |
|---|------|-----------------|------|-------|
| 2.1 | Poll `playlist.m3u8` 10 times at 1 s intervals; compare `EXT-X-MEDIA-SEQUENCE` | Sequence number increments on each poll (no stale repeats) | | |
| 2.2 | Download 5 consecutive segments and check for discontinuities | No `EXT-X-DISCONTINUITY` tag in segment list unless expected | | |
| 2.3 | Inspect segment timestamps with `ffprobe -show_packets` | PTS/DTS values are monotonically increasing across segments | | |
| 2.4 | Verify no missing segment gaps in playlist | Consecutive sequence numbers with no gaps | | |
| 2.5 | Confirm `EXT-X-MAP` init segment is referenced in playlist | `EXT-X-MAP` URI present for fMP4 playlist | | |
| 2.6 | Confirm init segment (`init.mp4` or equivalent) is downloadable | HTTP 200 on init segment URL | | |
| 2.7 | Verify playlist `EXT-X-TARGETDURATION` ≤ stated segment durations | `TARGETDURATION` ≥ actual max segment duration in playlist | | |
| 2.8 | Confirm partial segments have `DURATION` ≤ 500 ms | Each `EXT-X-PART` `DURATION` attribute ≤ 0.5 | | |

---

## Phase 3 — Client Playback Tests

### 3.1 iOS — Safari / AVPlayer

| # | Test | Expected Result | Pass | Notes |
|---|------|-----------------|------|-------|
| 3.1.1 | Open stream URL in iOS Safari | Playback starts within 5 s with no error dialog | | |
| 3.1.2 | Confirm video renders without artefacts for 60 s | No visible macroblocking, freezing, or grey frames | | |
| 3.1.3 | Confirm audio (if configured) plays in sync | Audio lag < 200 ms relative to video | | |
| 3.1.4 | Lock and unlock iPhone; stream resumes | Playback recovers within 5 s of screen unlock | | |
| 3.1.5 | Background the app for 10 s, return to foreground | Playback resumes within 5 s | | |
| 3.1.6 | Test on iOS 16 and iOS 17 if available | Playback succeeds on both versions | | |
| 3.1.7 | Test natively with `AVPlayer` + `AVPlayerViewController` (if applicable) | Video plays without errors in AVPlayer | | |

### 3.2 Browser — Chrome / Firefox with hls.js

| # | Test | Expected Result | Pass | Notes |
|---|------|-----------------|------|-------|
| 3.2.1 | Open web client at `http://localhost:3000` (or production URL) | Page loads without console errors related to HLS | | |
| 3.2.2 | Trigger camera stream start in the web UI | `Hls` instance attaches, `MANIFEST_PARSED` event fires in console | | |
| 3.2.3 | Confirm video element shows live video within 5 s | Video visible, not a black frame or placeholder | | |
| 3.2.4 | Open browser DevTools → Network; filter `.m3u8` requests | Playlist requests occurring roughly every 1–2 s | | |
| 3.2.5 | Check for `hls.js` error events in console | Zero `hlsError` (level = fatal) events after playback starts | | |
| 3.2.6 | Disable network for 5 s (DevTools throttle → offline); re-enable | `hls.js` recovers and resumes playback within 10 s | | |
| 3.2.7 | Test in Chrome latest and Firefox latest | Playback succeeds in both | | |
| 3.2.8 | Test in Safari desktop (uses native HLS, not hls.js) | Playback succeeds in Safari without requiring hls.js fallback | | |

### 3.3 Web Client (`clients/web/`) — Specific Checks

| # | Test | Expected Result | Pass | Notes |
|---|------|-----------------|------|-------|
| 3.3.1 | `NEXT_PUBLIC_HLS_STREAM_URL` is set in `.env.local` | Env var present; web client uses it to initialise `Hls` | | |
| 3.3.2 | Camera panel shows "Connected" status when stream is active | UI state reflects active playback | | |
| 3.3.3 | Camera panel shows "Disconnected" or error indicator when Pi is offline | UI state reflects lost connection, does not crash | | |
| 3.3.4 | No unhandled React errors in the console during connect/disconnect cycle | Zero `Uncaught` React errors in browser console | | |

---

## Phase 4 — LAN Playback and Latency

| # | Test | Expected Result | Pass | Notes |
|---|------|-----------------|------|-------|
| 4.1 | Play stream over LAN on iOS Safari and measure latency | End-to-end latency ≤ 4 s (LL-HLS target) | | |
| 4.2 | Play stream over LAN on browser (hls.js) and measure latency | End-to-end latency ≤ 4 s | | |
| 4.3 | Play stream over LAN for 5 minutes without manual intervention | No rebuffering events (spinner visible in player) | | |
| 4.4 | Simultaneously stream to iOS and browser on LAN | Both clients play stably; Pi CPU < 50% | | |
| 4.5 | Use a visual clocking method (Pi display shows timestamp; compare with client) to measure latency | Latency figure matches or beats § 4.1/4.2 measurements | | |

**Latency measurement method**: Display a digital clock or timestamp on the Pi (e.g. overlay generated in software), simultaneously capture the client screen and a reference clock, then calculate the difference. Alternatively, use `ffprobe -show_frames` to inspect PTS vs wall-clock timestamps.

---

## Phase 5 — WAN Playback and Latency

| # | Test | Expected Result | Pass | Notes |
|---|------|-----------------|------|-------|
| 5.1 | Expose Nginx over a public IP or VPN; play stream from an external network | Playback starts and is stable for at least 2 minutes | | |
| 5.2 | Measure end-to-end latency over WAN | Latency ≤ 8 s (WAN budget = LAN target + 4 s margin) | | |
| 5.3 | Simulate packet loss with `tc netem loss 2%`; observe player | Player does not crash; recovers within 15 s | | |
| 5.4 | Simulate 200 ms added RTT with `tc netem delay 200ms`; observe player | Playback continues; latency increase proportional to added RTT | | |
| 5.5 | Test HTTPS delivery if TLS is configured | HTTPS stream plays successfully; no cert errors | | |

---

## Phase 6 — Error and Edge Cases

| # | Test | Expected Result | Pass | Notes |
|---|------|-----------------|------|-------|
| 6.1 | Kill the HLS segmenter process while a client is playing | Player shows buffering or error state; does not crash browser/app | | |
| 6.2 | Restart the segmenter; confirm client recovers | Client resumes playback within 15 s of segmenter restart | | |
| 6.3 | Reboot the Raspberry Pi; confirm client recovers when Pi comes back | Client resumes within 30 s of Pi completing boot and restart of HLS pipeline | | |
| 6.4 | Fill HLS output disk to 95%; observe behaviour | Process logs a disk-full warning; segments roll over without crash | | |
| 6.5 | Feed a stale playlist to a fresh client (stop updating but keep Nginx running) | Client displays `MANIFEST_LOAD_ERROR` or equivalent; does not spin indefinitely | | |
| 6.6 | Request a non-existent segment URL manually | Nginx returns 404; client retries or errors gracefully | | |
| 6.7 | Start two simultaneous clients from a cold start | Both receive valid playlists; neither gets a corrupted segment | | |

---

## Phase 7 — Security Checks

| # | Test | Expected Result | Pass | Notes |
|---|------|-----------------|------|-------|
| 7.1 | Attempt to access HLS endpoint from an unintended origin (if CORS is restricted) | Request blocked with 403 or missing CORS header | | |
| 7.2 | Confirm TLS certificate is valid when HTTPS is enabled | No certificate warnings in browser or `curl` | | |
| 7.3 | Verify no directory listing is exposed by Nginx | `curl http://<pi-ip>/hls/` does not return a file listing | | |
| 7.4 | Confirm stream is not publicly accessible without auth if auth is configured | Unauthenticated request returns 401 or 403 | | |

---

## Sign-Off Criteria

All items below must be checked before the HLS milestone is considered complete:

- [ ] All Phase 1 tests pass (pipeline components healthy)
- [ ] All Phase 2 tests pass (playlist and segment integrity confirmed)
- [ ] iOS Safari playback works without errors (3.1.1 – 3.1.5)
- [ ] Browser playback with hls.js works without errors (3.2.1 – 3.2.6)
- [ ] LAN latency is ≤ 4 s end-to-end (Phase 4)
- [ ] At least one WAN test passes (5.1 or 5.5)
- [ ] Error/edge case tests 6.1 – 6.3 pass
- [ ] No open critical defects

**Sign-off date**: ___________
**Tested by**: ___________
**Pipeline version / commit**: ___________

---

## Test Results Template

Copy the table below into a test run document (e.g. `docs/test-runs/hls-YYYY-MM-DD.md`) to record results:

```markdown
## HLS Integration Test Run — YYYY-MM-DD

| Phase | # | Result (PASS / FAIL / SKIP) | Defect / Notes |
|-------|---|----------------------------|----------------|
| 1.1   | 1 | | |
| 1.1   | 2 | | |
...
```

---

## Related Documents

- [HLS Architecture Overview](./HLS.md)
- [HLS Runbook](./HLS_RUNBOOK.md)
- [System Architecture (ARC42)](./ARC42.md)
- [Product Requirements (PRD)](../requirements/PRD.md)
