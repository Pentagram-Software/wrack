# WebRTC Integration Test Checklist and Runbook

**Milestone**: M3-5 (WebRTC Streaming)  
**Issue**: PEN-70  
**Pre-requisites**: M3-1 (WebRTC pipeline), M3-2 (signaling server), M3-3 (browser client), M3-4 (reconnect + health)

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [Test Environment Requirements](#2-test-environment-requirements)
3. [Runbook — Service Startup](#3-runbook--service-startup)
4. [Integration Test Checklist — LAN](#4-integration-test-checklist--lan)
5. [Integration Test Checklist — WAN / NAT Traversal](#5-integration-test-checklist--wan--nat-traversal)
6. [Integration Test Checklist — Reconnect and Resilience](#6-integration-test-checklist--reconnect-and-resilience)
7. [Integration Test Checklist — Security](#7-integration-test-checklist--security)
8. [Latency Measurement Procedure](#8-latency-measurement-procedure)
9. [Health Endpoint Validation](#9-health-endpoint-validation)
10. [Pass/Fail Criteria Summary](#10-passfail-criteria-summary)
11. [Troubleshooting Guide](#11-troubleshooting-guide)
12. [Test Execution Log Template](#12-test-execution-log-template)

---

## 1. Purpose and Scope

This document defines the integration test checklist and operational runbook for validating the
WebRTC streaming pipeline delivered in Milestone M3. It covers:

- End-to-end WebRTC playback from Raspberry Pi camera to browser (`<video>` element)
- Signaling (SDP offer/answer) and ICE negotiation
- Video quality and latency (target < 500 ms on LAN)
- Reconnect behaviour after intentional network interruption
- DTLS/SRTP security verification
- Health endpoint correctness

**Out of scope**: HLS playback (see `docs/architecture/HLS.md`), iOS AVPlayer, AI frame
processing, multi-client load testing.

---

## 2. Test Environment Requirements

### 2.1 Hardware

| Item | Specification |
|------|---------------|
| Raspberry Pi | Pi 5 (4 GB+ recommended) |
| Camera | Pi Camera v2.1 |
| Test client machine | macOS or Linux laptop/desktop with Chrome ≥ 110 |
| Network switch | Gigabit Ethernet (for wired LAN tests) |
| Wi-Fi AP | 802.11ac/Wi-Fi 5 minimum (for wireless LAN tests) |

### 2.2 Software Versions to Record

Before starting, record the following in the [Test Execution Log](#12-test-execution-log-template):

```
Pi OS version      : ____________________
Python version     : ____________________
Picamera2 version  : ____________________
WebRTC stack       : GStreamer _____ / aiortc _____ (circle one)
GStreamer version  : ____________________  (if applicable)
aiortc version     : ____________________  (if applicable)
Browser            : Chrome / Firefox / Safari _____ version _____
Signaling server   : ____________________
```

### 2.3 Network Topology

Two test topologies must be covered:

**LAN topology (required)**:

```
[Raspberry Pi]──────[LAN switch/router]──────[Test browser machine]
  :8080 (signaling)                              Chrome / Firefox
  :9999 (WebRTC UDP, via ICE)
```

**WAN topology (required for full sign-off)**:

```
[Raspberry Pi]──[NAT router A]──[Internet]──[NAT router B]──[Test browser machine]
                  STUN: stun.l.google.com:19302 (or self-hosted)
                  TURN: configured in config file (if needed)
```

### 2.4 Environment Variables / Config File

Verify the following are set before each test run. Document actual values in the test log:

| Variable / Config key | Example value | Notes |
|-----------------------|---------------|-------|
| `SIGNALING_PORT` | `8080` | Signaling server listen port |
| `WEBRTC_STUN_URL` | `stun:stun.l.google.com:19302` | STUN server for ICE |
| `WEBRTC_TURN_URL` | `turn:<host>:<port>` | Required for symmetric NAT |
| `WEBRTC_TURN_USER` | — | TURN credential (from config, not env) |
| `WEBRTC_TURN_PASS` | — | TURN credential (from config, not env) |
| `API_KEY` | — | Signaling auth header value |
| `VIDEO_BITRATE_KBPS` | `2000` | H.264 target bitrate |
| `VIDEO_WIDTH` | `1280` | Capture resolution |
| `VIDEO_HEIGHT` | `720` | Capture resolution |
| `VIDEO_FPS` | `30` | Capture frame rate |
| `KEYFRAME_INTERVAL` | `30` | Frames between keyframes |

---

## 3. Runbook — Service Startup

This section is the step-by-step operational guide for starting all services required for
integration testing. Follow these steps in order before running any checklist item.

### Step 1: Prepare the Raspberry Pi

```bash
# 1a. SSH into the Pi
ssh pi@<pi-ip-address>

# 1b. Navigate to the streamer directory
cd ~/wrack/edge/video-streamer

# 1c. Activate the Python virtual environment
source .venv/bin/activate

# 1d. Copy and edit the config file
cp config/config.json config/config.local.json
# Edit config.local.json: set bitrate, resolution, FPS, STUN/TURN URLs

# 1e. Verify the camera is accessible
python3 -c "from picamera2 import Picamera2; cam = Picamera2(); cam.start(); print('Camera OK'); cam.stop()"
# Expected output: "Camera OK"
```

### Step 2: Start the WebRTC Pipeline and Signaling Server

```bash
# 2a. Start the combined WebRTC streamer (pipeline + signaling)
python3 streamer.py --mode webrtc --config config/config.local.json
# Expected: "Signaling server listening on :8080"
# Expected: "WebRTC pipeline ready"

# 2b. Verify the signaling endpoint is reachable from the Pi itself
curl -s http://localhost:8080/health
# Expected: {"streaming": false, "clients": 0}
```

### Step 3: Verify Signaling Reachability from Test Machine

```bash
# Run on test machine (not Pi)
curl -s http://<pi-ip>:8080/health
# Expected: {"streaming": false, "clients": 0}

# If API key is required:
curl -s -H "X-API-Key: <key>" http://<pi-ip>:8080/health
```

If this fails:
- Check firewall: `sudo ufw status` on Pi; ensure port 8080 is open
- Check Pi IP: `ip addr show` on Pi

### Step 4: Open the Browser Client

```bash
# Option A: Standalone HTML demo (M3-3 deliverable)
open http://<pi-ip>:8080/client.html   # or the path served by signaling server

# Option B: web app (clients/web)
cd ~/wrack/clients/web
cp .env.local.example .env.local
# Set NEXT_PUBLIC_WEBRTC_SIGNALING_URL=http://<pi-ip>:8080
npm run dev
open http://localhost:3000
# Navigate to camera view
```

### Step 5: Initiate Connection

In the browser client, click **"Connect"** (or equivalent). Observe:

- Browser DevTools → Console: no errors
- Browser DevTools → Network: `GET /offer` request to signaling server returns HTTP 200 with SDP
- Browser DevTools → `RTCPeerConnection` in application: connection state transitions to `connected`

---

## 4. Integration Test Checklist — LAN

Run these tests with the Pi and test machine on the same subnet (wired or Wi-Fi).

### TC-LAN-001: Signaling — Offer/Answer Exchange

| Field | Value |
|-------|-------|
| **Pre-condition** | Streamer and signaling server running (Step 3 above) |
| **Action** | Click "Connect" in browser; capture signaling traffic in DevTools |
| **Expected** | `GET /offer` returns HTTP 200 with valid SDP containing `video`, `a=rtpmap:96 H264` |
| **Pass criterion** | SDP contains `m=video`, `a=rtpmap:96 H264/90000`, `a=fingerprint` (DTLS), at least one `a=candidate` line |
| **Fail action** | Record SDP in test log; check pipeline logs for ICE gather errors |
| **Result** | ☐ Pass  ☐ Fail  Notes: __________________ |

### TC-LAN-002: ICE Negotiation — Connection Established

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-001 passed |
| **Action** | Open `chrome://webrtc-internals` (or `about:webrtc` in Firefox); observe ICE state |
| **Expected** | `iceConnectionState` transitions: `new → checking → connected` within 5 s |
| **Pass criterion** | Final state is `connected` or `completed`; at least one candidate pair is nominated |
| **Fail action** | Record nominated candidate type (host/srflx/relay) and any errors |
| **Result** | ☐ Pass  ☐ Fail  Notes: __________________ |

### TC-LAN-003: Video Playback — Frame Rendering

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-002 passed |
| **Action** | Observe `<video>` element in browser |
| **Expected** | Live video from Pi camera begins playing within 5 s of ICE connected |
| **Pass criterion** | `<video>.currentTime` is increasing; visible camera frames are rendered |
| **Fail action** | Check `RTCInboundRtpStreamStats.framesReceived` and `framesDecoded` |
| **Result** | ☐ Pass  ☐ Fail  Notes: __________________ |

### TC-LAN-004: Video Quality — Frame Rate

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-003 passed; stream running for ≥ 30 s |
| **Action** | Read `framesPerSecond` from `RTCInboundRtpStreamStats` in `chrome://webrtc-internals` |
| **Expected** | ≥ 25 FPS sustained |
| **Pass criterion** | Average FPS over 30 s window ≥ 25 FPS; no freeze > 1 s |
| **Fail action** | Record encoder stats from Pi health endpoint; check CPU usage |
| **Result** | ☐ Pass  ☐ Fail  FPS measured: _____ |

### TC-LAN-005: Video Quality — No Visible Artefacts

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-003 passed |
| **Action** | Visual inspection of stream for 60 s |
| **Expected** | No persistent blocking, green tiling, or frame corruption |
| **Pass criterion** | Any artefacts are brief (< 1 s) and self-correct; not persistent |
| **Fail action** | Capture screenshot of artefact; check keyframe interval and bitrate |
| **Result** | ☐ Pass  ☐ Fail  Notes: __________________ |

### TC-LAN-006: Latency — End-to-End < 500 ms

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-003 passed |
| **Action** | Follow **Latency Measurement Procedure** (§8) |
| **Expected** | End-to-end latency < 500 ms |
| **Pass criterion** | Median latency across 5 measurements < 500 ms; no measurement > 750 ms |
| **Fail action** | Record latency values; compare with `RTCInboundRtpStreamStats.jitterBufferDelay` |
| **Result** | ☐ Pass  ☐ Fail  Latency measurements (ms): ___, ___, ___, ___, ___ |

### TC-LAN-007: Audio (if applicable)

| Field | Value |
|-------|-------|
| **Pre-condition** | Audio is configured in encoding pipeline |
| **Action** | Verify audio track in SDP; listen for audio in browser |
| **Expected** | `m=audio` line in SDP; audible output from browser |
| **Pass criterion** | Audio and video are synchronised (no noticeable drift over 60 s) |
| **Result** | ☐ Pass  ☐ Fail  ☐ N/A (audio not implemented) |

### TC-LAN-008: Multi-Tab / Multi-Client

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-003 passed with one client |
| **Action** | Open a second browser tab and connect |
| **Expected** | Both tabs receive video simultaneously; health endpoint shows `"clients": 2` |
| **Pass criterion** | No degradation in either stream (FPS, latency); health count is correct |
| **Result** | ☐ Pass  ☐ Fail  Notes: __________________ |

---

## 5. Integration Test Checklist — WAN / NAT Traversal

> **Note**: These tests require the Pi to be behind NAT router A and the test machine behind
> NAT router B, or equivalent. If a VPN is used to simulate WAN, document this.

### TC-WAN-001: STUN — Server-Reflexive Candidate Used

| Field | Value |
|-------|-------|
| **Pre-condition** | STUN server URL configured; Pi behind NAT |
| **Action** | Connect from a machine outside Pi's NAT; check `chrome://webrtc-internals` → ICE candidates |
| **Expected** | `srflx` candidate type in the nominated candidate pair |
| **Pass criterion** | Connection established using at least one `srflx` candidate; video plays |
| **Result** | ☐ Pass  ☐ Fail  Candidate type used: __________________ |

### TC-WAN-002: WAN Playback — Video Renders

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-WAN-001 passed |
| **Action** | Same as TC-LAN-003 but from WAN machine |
| **Expected** | Live video renders within 10 s of ICE connected |
| **Pass criterion** | `<video>.currentTime` increasing; visible frames |
| **Result** | ☐ Pass  ☐ Fail  Notes: __________________ |

### TC-WAN-003: WAN Latency — Target < 1 s

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-WAN-002 passed |
| **Action** | Follow **Latency Measurement Procedure** (§8) from WAN machine |
| **Expected** | End-to-end latency < 1 s (STUN path); < 2 s (TURN relay path) |
| **Pass criterion** | Median latency across 5 measurements within target |
| **Result** | ☐ Pass  ☐ Fail  Latency measurements (ms): ___, ___, ___, ___, ___ |

### TC-WAN-004: TURN Relay Fallback (if symmetric NAT present)

| Field | Value |
|-------|-------|
| **Pre-condition** | TURN server URL and credentials configured in config file |
| **Action** | Block direct UDP between Pi and test machine; confirm TURN relay used |
| **Expected** | ICE uses `relay` candidate type; connection still established |
| **Pass criterion** | Video plays via TURN relay; `relay` candidate visible in `webrtc-internals` |
| **Fail action** | Verify TURN credentials; check Coturn server logs |
| **Result** | ☐ Pass  ☐ Fail  ☐ N/A (symmetric NAT not in scope) |

### TC-WAN-005: WAN Frame Rate

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-WAN-002 passed; stream running ≥ 30 s |
| **Action** | Read FPS from `RTCInboundRtpStreamStats.framesPerSecond` |
| **Expected** | ≥ 20 FPS sustained (lower bar than LAN due to bandwidth variability) |
| **Result** | ☐ Pass  ☐ Fail  FPS measured: _____ |

---

## 6. Integration Test Checklist — Reconnect and Resilience

### TC-RC-001: Graceful Browser Disconnect and Reconnect

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-003 passed |
| **Action** | Click "Disconnect" in browser client; wait 5 s; click "Connect" again |
| **Expected** | New signaling exchange completes; video resumes within 5 s |
| **Pass criterion** | Full reconnect cycle < 5 s; no browser reload required |
| **Result** | ☐ Pass  ☐ Fail  Reconnect time (s): _____ |

### TC-RC-002: Network Interruption — Pi-Side

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-003 passed |
| **Action** | Disable Pi's network interface: `sudo ip link set eth0 down`; wait 10 s; re-enable: `sudo ip link set eth0 up` |
| **Expected** | Browser shows reconnecting state; video resumes without manual refresh |
| **Pass criterion** | Auto-reconnect completes within 30 s of network restoration; no browser reload |
| **Fail action** | Record ICE connection state transitions from `chrome://webrtc-internals` |
| **Result** | ☐ Pass  ☐ Fail  Time to restore (s): _____ |

### TC-RC-003: Network Interruption — Client-Side

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-003 passed |
| **Action** | Disable test machine's network interface for 10 s; re-enable |
| **Expected** | Video resumes within 30 s; Pi health endpoint shows client count recovery |
| **Pass criterion** | Stream resumes; `clients` count in health reflects correct state after reconnect |
| **Result** | ☐ Pass  ☐ Fail  Time to restore (s): _____ |

### TC-RC-004: ICE Restart on Connection Failure

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-RC-002 or TC-RC-003 passes |
| **Action** | Inspect browser console and `chrome://webrtc-internals` during reconnect |
| **Expected** | `iceConnectionState` transitions to `failed` → client triggers ICE restart → `connected` |
| **Pass criterion** | ICE restart is triggered automatically (no user action); state recovers to `connected` |
| **Result** | ☐ Pass  ☐ Fail  Notes: __________________ |

### TC-RC-005: Pi Streamer Restart

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-003 passed |
| **Action** | Kill the Pi streamer process: `pkill -f streamer.py`; restart it after 5 s |
| **Expected** | Browser client reconnects automatically after streamer restarts |
| **Pass criterion** | Video resumes within 30 s of streamer restart; no manual browser action required |
| **Result** | ☐ Pass  ☐ Fail  Time to restore (s): _____ |

### TC-RC-006: Exponential Back-Off on Repeated Failure

| Field | Value |
|-------|-------|
| **Pre-condition** | Client reconnect logic implements exponential back-off (M3-4) |
| **Action** | Keep Pi network down for 120 s while observing browser console reconnect attempts |
| **Expected** | Retry intervals follow back-off schedule: ~1 s, 2 s, 4 s, 8 s, … (max ≤ 30 s) |
| **Pass criterion** | No reconnect attempt faster than 1 s after first failure; intervals increase |
| **Result** | ☐ Pass  ☐ Fail  Observed intervals (s): __________________ |

---

## 7. Integration Test Checklist — Security

### TC-SEC-001: DTLS Handshake Verified

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-002 passed |
| **Action** | In `chrome://webrtc-internals`, check `RTCCertificate` and `dtlsState` |
| **Expected** | `dtlsState: "connected"`; certificate fingerprint in SDP matches negotiated fingerprint |
| **Pass criterion** | DTLS state is `connected` for the active transport |
| **Result** | ☐ Pass  ☐ Fail  Notes: __________________ |

### TC-SEC-002: SRTP — Encrypted Media

| Field | Value |
|-------|-------|
| **Pre-condition** | TC-LAN-003 passed |
| **Action** | Capture UDP traffic with `tcpdump` during active stream; inspect packet content |
| **Expected** | RTP payloads are not readable as raw H.264 NAL units (encrypted via SRTP) |
| **Pass criterion** | No unencrypted H.264 start codes (`00 00 00 01`) visible at the beginning of UDP payloads |
| **Command** | `sudo tcpdump -i eth0 -nn udp and host <pi-ip> -w /tmp/webrtc-capture.pcap` |
| **Result** | ☐ Pass  ☐ Fail  Notes: __________________ |

### TC-SEC-003: Signaling API Key Authentication

| Field | Value |
|-------|-------|
| **Pre-condition** | Signaling server requires `X-API-Key` header |
| **Action** | Attempt `GET /offer` without `X-API-Key` header |
| **Expected** | HTTP 401 returned; no SDP leakage |
| **Command** | `curl -v http://<pi-ip>:8080/offer` |
| **Pass criterion** | Response is HTTP 401; response body does not contain SDP |
| **Result** | ☐ Pass  ☐ Fail  Notes: __________________ |

### TC-SEC-004: HTTPS Signaling (WAN / internet-exposed only)

| Field | Value |
|-------|-------|
| **Pre-condition** | Signaling server exposed to internet with TLS configured |
| **Action** | Attempt `GET /offer` over HTTP (not HTTPS) |
| **Expected** | HTTP request is rejected or redirected to HTTPS |
| **Pass criterion** | Plaintext HTTP does not return SDP |
| **Result** | ☐ Pass  ☐ Fail  ☐ N/A (LAN-only deployment) |

---

## 8. Latency Measurement Procedure

End-to-end latency is measured using a **clock overlay method**: the Pi camera captures a
high-resolution clock face or timestamp display, and the browser rendering delay is compared
against the reference clock.

### Option A: Phone Clock Method (no Pi code changes required)

1. Place a smartphone displaying a stopwatch/clock app in view of the Pi camera.
2. On the same test machine, open the browser client with the WebRTC stream.
3. Take a screenshot (or use screen recording) capturing both the browser window and the
   phone's clock display simultaneously (e.g. side-by-side on the same screen).
4. Compare the time shown in the stream vs. the real clock reading at that moment.
5. Repeat 5 times; record each delta.

```
Latency = (clock time visible in stream) vs. (current real time at screenshot moment)
```

### Option B: Timestamp Overlay Script (Pi-side)

If the Pi encoder supports frame injection, use a script to burn the current timestamp
(millisecond precision) into each frame as an overlay:

```python
# Add to edge/video-streamer: draw timestamp onto frame before encoding
import cv2, time
frame_with_ts = cv2.putText(
    frame,
    f"{time.time_ns() // 1_000_000}",   # ms since epoch
    (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2
)
```

Then compare the timestamp visible in the browser stream to `Date.now()` in the browser
console at the moment of capture:

```javascript
// Browser console: measure latency from visible timestamp
// 1. Pause the <video> element or take a screenshot
// 2. Read the millisecond timestamp visible in the frozen frame
// 3. latency = Date.now() - <timestamp_in_frame>
```

### Option C: webrtc-internals Stats

As a supplementary (not primary) measurement, read from `chrome://webrtc-internals`:

- `RTCInboundRtpStreamStats.jitterBufferDelay` — jitter buffer contribution
- `RTCInboundRtpStreamStats.jitterBufferMinimumDelay` — minimum observed

These do not include encoding or network delay, so use only as a floor/lower-bound estimate.

### Recording Latency Results

| Measurement # | Timestamp shown in stream (ms) | Real time at screenshot (ms) | Delta (ms) |
|--------------|-------------------------------|------------------------------|-----------|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| **Median** | | | |

---

## 9. Health Endpoint Validation

The Pi must expose a health endpoint at `GET /health` (M3-4). Run these checks while
the stream is active.

### TC-HEALTH-001: Health Endpoint Responds

```bash
curl -s http://<pi-ip>:8080/health | python3 -m json.tool
```

**Expected response schema**:
```json
{
  "streaming": true,
  "clients": 1,
  "fps": 29.8,
  "bitrate_kbps": 1987,
  "uptime_s": 143
}
```

| Check | Expected | Pass |
|-------|----------|------|
| HTTP status | 200 | ☐ |
| `streaming` field | `true` while stream is active | ☐ |
| `clients` field | Matches connected client count | ☐ |
| `fps` field | Within ±5 of configured FPS | ☐ |
| `bitrate_kbps` field | Within ±20% of configured bitrate | ☐ |

### TC-HEALTH-002: Health Shows No Clients When Idle

```bash
# Disconnect all browser tabs
curl -s http://<pi-ip>:8080/health | python3 -m json.tool
```

| Check | Expected | Pass |
|-------|----------|------|
| `streaming` field | `false` or `true` (Pi still running, no clients) | ☐ |
| `clients` field | `0` | ☐ |

### TC-HEALTH-003: Client Count Updates After Connect/Disconnect

1. Connect browser client → check `clients` = 1  
2. Open second tab → check `clients` = 2  
3. Close second tab → check `clients` = 1  
4. Close first tab → check `clients` = 0  

| Step | Expected `clients` | Pass |
|------|-------------------|------|
| After first connect | 1 | ☐ |
| After second connect | 2 | ☐ |
| After closing second | 1 | ☐ |
| After closing first | 0 | ☐ |

---

## 10. Pass/Fail Criteria Summary

The M3-5 integration test suite is considered **passed** when all mandatory items are green.
Optional items should be tracked but do not block M3 sign-off.

### Mandatory (M3 sign-off required)

| Test ID | Description | Result |
|---------|-------------|--------|
| TC-LAN-001 | Signaling offer/answer exchange | ☐ Pass ☐ Fail |
| TC-LAN-002 | ICE negotiation — connection established | ☐ Pass ☐ Fail |
| TC-LAN-003 | Video playback — frame rendering | ☐ Pass ☐ Fail |
| TC-LAN-004 | LAN frame rate ≥ 25 FPS | ☐ Pass ☐ Fail |
| TC-LAN-006 | LAN latency < 500 ms | ☐ Pass ☐ Fail |
| TC-WAN-001 | STUN / server-reflexive candidate | ☐ Pass ☐ Fail |
| TC-WAN-002 | WAN video playback | ☐ Pass ☐ Fail |
| TC-RC-001 | Graceful disconnect + reconnect | ☐ Pass ☐ Fail |
| TC-RC-002 | Network interruption (Pi-side) | ☐ Pass ☐ Fail |
| TC-RC-004 | ICE restart on connection failure | ☐ Pass ☐ Fail |
| TC-SEC-001 | DTLS handshake verified | ☐ Pass ☐ Fail |
| TC-SEC-002 | SRTP encrypted media | ☐ Pass ☐ Fail |
| TC-SEC-003 | Signaling API key auth | ☐ Pass ☐ Fail |
| TC-HEALTH-001 | Health endpoint responds correctly | ☐ Pass ☐ Fail |
| TC-HEALTH-003 | Client count updates dynamically | ☐ Pass ☐ Fail |

### Optional (tracked; do not block M3)

| Test ID | Description | Result |
|---------|-------------|--------|
| TC-LAN-005 | No visible video artefacts | ☐ Pass ☐ Fail ☐ N/A |
| TC-LAN-007 | Audio playback | ☐ Pass ☐ Fail ☐ N/A |
| TC-LAN-008 | Multi-client simultaneous streams | ☐ Pass ☐ Fail ☐ N/A |
| TC-WAN-003 | WAN latency < 1 s | ☐ Pass ☐ Fail |
| TC-WAN-004 | TURN relay fallback | ☐ Pass ☐ Fail ☐ N/A |
| TC-WAN-005 | WAN frame rate ≥ 20 FPS | ☐ Pass ☐ Fail |
| TC-RC-003 | Network interruption (client-side) | ☐ Pass ☐ Fail |
| TC-RC-005 | Pi streamer restart recovery | ☐ Pass ☐ Fail |
| TC-RC-006 | Exponential back-off on failure | ☐ Pass ☐ Fail |
| TC-SEC-004 | HTTPS signaling (WAN only) | ☐ Pass ☐ Fail ☐ N/A |
| TC-HEALTH-002 | Health idle state | ☐ Pass ☐ Fail |

---

## 11. Troubleshooting Guide

### Problem: `GET /offer` returns HTTP 404 or connection refused

**Cause**: Signaling server not running, or wrong port.  
**Fix**:
```bash
# On Pi: verify the process is running
ps aux | grep streamer.py
# Verify the port is listening
ss -tlnp | grep 8080
# Restart if needed
python3 streamer.py --mode webrtc --config config/config.local.json
```

---

### Problem: ICE stays in `checking` state indefinitely

**Cause**: Firewall blocking UDP, STUN server unreachable, or NAT prevents direct path.  
**Fix**:
```bash
# Test STUN reachability from Pi
python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0])"

# Check UDP ports are open on Pi
sudo ufw status
sudo ufw allow 10000:65535/udp   # WebRTC ephemeral ports

# If on WAN, configure TURN server in config.local.json
```

---

### Problem: Video does not render (ICE connected, but black `<video>` element)

**Cause**: Codec mismatch, H.264 profile not supported by browser, or RTP pipeline bug.  
**Fix**:
- Verify SDP contains `a=rtpmap:96 H264/90000`
- Switch to `baseline` profile in encoder config
- Check `chrome://webrtc-internals` → `RTCInboundRtpStreamStats.framesReceived` vs `framesDecoded`
- If `framesReceived > 0` but `framesDecoded == 0`: decoder error — check H.264 NAL unit format

---

### Problem: Video is choppy or freezes (FPS drops below 10)

**Cause**: Pi CPU overload, bitrate too high for network, or jitter buffer issues.  
**Fix**:
```bash
# Check Pi CPU usage during stream
top -bn1 | grep python

# Reduce bitrate in config (e.g., 1000 kbps)
# Reduce resolution (e.g., 640x480)
# Verify HW encoder is active (check encoder log output)
```

---

### Problem: Latency > 500 ms on LAN

**Cause**: Jitter buffer delay too large, keyframe interval too long, or network congestion.  
**Fix**:
- Reduce `jitterBufferDelay` by reducing keyframe interval (e.g., 15 frames)
- Use wired Ethernet instead of Wi-Fi on test machine
- Check for background traffic: `iftop -i eth0` on Pi
- Verify encoder is using HW acceleration (SW encode adds 50–100 ms)

---

### Problem: DTLS handshake fails (`dtlsState: "failed"`)

**Cause**: Clock skew > 5 min between Pi and client, or TLS cert issue.  
**Fix**:
```bash
# Sync Pi clock
sudo ntpdate -u pool.ntp.org
# Or
sudo timedatectl set-ntp on
```

---

### Problem: `clients` count in health endpoint does not decrement after browser disconnect

**Cause**: Signaling server does not track WebRTC connection teardown.  
**Fix**: Ensure `iceConnectionState === "disconnected"/"failed"/"closed"` events trigger
client deregistration in the signaling server and pipeline.

---

### Problem: No reconnect after network interruption (TC-RC-002 fails)

**Cause**: Client reconnect logic not implemented or ICE restart not triggered.  
**Fix**: Verify M3-4 deliverable: client listens for `iceConnectionState === "failed"` and
calls `peerConnection.restartIce()` followed by a new offer/answer exchange with the
signaling server.

---

## 12. Test Execution Log Template

Copy this template for each test run. Fill in all fields.

```
# WebRTC Integration Test Execution Log

Date:           ____________________
Tester:         ____________________
Milestone:      M3 (WebRTC Streaming)
Issue:          PEN-70

## Environment

Pi OS version:           ____________________
Python version:          ____________________
Picamera2 version:       ____________________
WebRTC stack:            GStreamer _____ / aiortc _____ (circle one)
GStreamer version:       ____________________  (if applicable)
aiortc version:          ____________________  (if applicable)
Signaling server commit: ____________________
Browser:                 ____________________  version: ____________
Network topology:        LAN wired / LAN Wi-Fi / WAN (circle all that apply)
STUN server:             ____________________
TURN server:             ____________________ (or N/A)
Config file path:        ____________________
Video bitrate (kbps):    ____________________
Resolution:              ____________________
FPS:                     ____________________

## LAN Test Results

TC-LAN-001:  ☐ Pass  ☐ Fail  Notes: ____________________
TC-LAN-002:  ☐ Pass  ☐ Fail  Notes: ____________________
TC-LAN-003:  ☐ Pass  ☐ Fail  Notes: ____________________
TC-LAN-004:  ☐ Pass  ☐ Fail  FPS: _______
TC-LAN-005:  ☐ Pass  ☐ Fail  ☐ N/A
TC-LAN-006:  ☐ Pass  ☐ Fail  Latency (ms): ___, ___, ___, ___, ___ Median: ___
TC-LAN-007:  ☐ Pass  ☐ Fail  ☐ N/A
TC-LAN-008:  ☐ Pass  ☐ Fail  ☐ N/A

## WAN Test Results

TC-WAN-001:  ☐ Pass  ☐ Fail  ☐ N/A  Candidate type: ____________
TC-WAN-002:  ☐ Pass  ☐ Fail  ☐ N/A
TC-WAN-003:  ☐ Pass  ☐ Fail  ☐ N/A  Latency (ms): ___, ___, ___, ___, ___ Median: ___
TC-WAN-004:  ☐ Pass  ☐ Fail  ☐ N/A
TC-WAN-005:  ☐ Pass  ☐ Fail  ☐ N/A  FPS: _______

## Reconnect Test Results

TC-RC-001:  ☐ Pass  ☐ Fail  Reconnect time (s): _______
TC-RC-002:  ☐ Pass  ☐ Fail  Time to restore (s): _______
TC-RC-003:  ☐ Pass  ☐ Fail  ☐ N/A  Time to restore (s): _______
TC-RC-004:  ☐ Pass  ☐ Fail
TC-RC-005:  ☐ Pass  ☐ Fail  ☐ N/A  Time to restore (s): _______
TC-RC-006:  ☐ Pass  ☐ Fail  ☐ N/A  Observed intervals: ____________________

## Security Test Results

TC-SEC-001:  ☐ Pass  ☐ Fail
TC-SEC-002:  ☐ Pass  ☐ Fail
TC-SEC-003:  ☐ Pass  ☐ Fail
TC-SEC-004:  ☐ Pass  ☐ Fail  ☐ N/A

## Health Endpoint Results

TC-HEALTH-001:  ☐ Pass  ☐ Fail
TC-HEALTH-002:  ☐ Pass  ☐ Fail  ☐ N/A
TC-HEALTH-003:  ☐ Pass  ☐ Fail

## Overall Sign-off

Mandatory items passing:  ___ / 15
Optional items passing:   ___ / 11

M3 Integration Test:  ☐ PASSED  ☐ FAILED  ☐ INCOMPLETE

Sign-off notes:
____________________
____________________
```
