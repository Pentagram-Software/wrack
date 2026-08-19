# WebRTC Streaming Architecture

This document describes the WebRTC streaming mode for the Raspberry Pi Camera Streamer
(Milestone M3). It complements `HLS.md` and provides the architectural reference for the
integration test checklist and runbook in `docs/testing/webrtc-integration-checklist.md`.

## 1. What We Use and Why

- **Protocol**: WebRTC (browser-native, peer-to-peer media)
- **Goal**: Sub-500 ms end-to-end latency for real-time robot camera viewing in the browser
- **Transport**: DTLS/SRTP over UDP; ICE for NAT traversal
- **Signaling**: Minimal HTTP or WebSocket offer/answer exchange

WebRTC is preferred over HLS when real-time viewing latency matters (e.g. remote robot
control where camera delay affects operation). HLS (2–4 s) is sufficient for casual
monitoring; WebRTC (< 500 ms) is required for interactive control.

## 2. Media Pipeline (High-Level)

```
Pi Camera v2.1
      │
      ▼
Picamera2 capture (1280×720 @ 30 FPS)
      │
      ▼
H.264 encoder (HW-accelerated, baseline/main profile)
  • bitrate: configurable (default 2 Mbit/s)
  • GOP: ~30 frames (1 s keyframe interval)
      │
      ▼
RTP packetiser (RFC 6184 — H.264 over RTP)
      │
      ▼ DTLS/SRTP (SRTP encryption, DTLS key exchange)
WebRTC pipeline (GStreamer webrtcbin or aiortc)
      │  (UDP, ICE-negotiated path)
      ▼
Browser (RTCPeerConnection + <video> element)
```

## 3. Component Responsibilities

| Component | Role | Stack choice |
|-----------|------|--------------|
| **Pi capture** | Picamera2, configurable res/FPS | Picamera2 |
| **Encoder** | H.264/AVC HW-accelerated | Picamera2 H264Encoder |
| **WebRTC pipeline** | RTP packetisation, ICE, DTLS/SRTP | GStreamer `webrtcbin` **or** `aiortc` (M0-3 decision) |
| **Signaling server** | SDP offer/answer, ICE candidate exchange | Minimal HTTP or WebSocket (Python/aiohttp) |
| **STUN server** | ICE reflexive address discovery | Public STUN (Google) on LAN; self-hosted for production |
| **TURN server** | Relay for symmetric NAT | Optional for WAN; required if direct UDP is blocked |
| **Browser client** | `RTCPeerConnection`, `<video>` playback | HTML/JS (Vanilla or integrated into `clients/web/CameraView`) |

## 4. Signaling Flow

```
Browser                        Signaling Server                   Pi WebRTC Pipeline
   │                                  │                                  │
   │── GET /offer ─────────────────►  │                                  │
   │                                  │── trigger offer ───────────────► │
   │                                  │◄── SDP offer (H.264 video) ───── │
   │◄── SDP offer ───────────────────  │                                  │
   │                                  │                                  │
   │── POST /answer (SDP answer) ───► │                                  │
   │                                  │── forward answer ──────────────► │
   │                                  │                                  │
   │  (ICE candidates exchanged via same signaling channel)             │
   │                                  │                                  │
   │◄══════════════════ DTLS/SRTP RTP media (UDP) ══════════════════════ │
   │  <video>.play()                  │                                  │
```

## 5. ICE and NAT Traversal Strategy

- **LAN (same subnet)**: host ICE candidates — direct UDP, no STUN/TURN required.
- **LAN (different VLANs) / simple NAT**: server-reflexive candidates via STUN.
  - Default STUN: `stun:stun.l.google.com:19302`
- **WAN / symmetric NAT**: TURN relay required for guaranteed connectivity.
  - TURN credentials stored in config file (not hard-coded).
- ICE timeout: 5 s default; increase to 10 s for WAN tests.

## 6. Encoding Parameters for WebRTC

| Parameter | Recommended value | Reason |
|-----------|-------------------|--------|
| Profile | `baseline` or `main` | Broad browser compatibility |
| Keyframe interval | ≤ 1 s (30 frames @ 30 FPS) | Fast seek + reconnect |
| Bitrate | 1–3 Mbit/s (start 2 Mbit/s) | Balance quality vs latency |
| Resolution | 1280×720 (720p) or 640×480 (480p) | Pi 5 HW capability |
| Frame rate | 30 FPS | Smooth robot camera view |
| RTP payload type | 96 (dynamic, H.264) | RFC 6184 |

## 7. Reconnect and Health Checks (M3-4)

- **ICE restart**: on `iceconnectionstate === "failed"` trigger ICE restart via re-signaling.
- **Offer retry**: exponential back-off (1 s, 2 s, 4 s, max 30 s).
- **Health endpoint**: Pi exposes `GET /health` returning `{"streaming": true, "clients": N,
  "fps": F, "bitrate_kbps": B}`.
- **Client watchdog**: if no RTP received for > 3 s, initiate reconnect.

## 8. Security

- **DTLS/SRTP**: mandatory for all WebRTC sessions (enforced by WebRTC spec).
- **Signaling**: HTTPS when internet-exposed; HTTP acceptable on trusted LAN.
- **API key**: signaling endpoint should require `X-API-Key` header (same key as robot
  control API) before returning an SDP offer.
- **STUN/TURN credentials**: store in config file, never hard-code.

## 9. Latency Targets

| Path | Target | Measurement method |
|------|--------|-------------------|
| LAN (same subnet) | < 500 ms | Clock overlay in video frames (see runbook §7) |
| WAN (via STUN) | < 1 s | Same as above |
| WAN (via TURN relay) | < 2 s | Acceptable degradation |

## 10. Relationship to Other Transports

```
Transport   Latency     Use case                     iOS  Browser
──────────  ─────────   ─────────────────────────    ───  ───────
UDP (raw)   ~50 ms      Lab/debug only               ✓    ✗ (no raw UDP)
HLS LL      2–4 s       Monitoring / iOS native      ✓    ✓
WebRTC      < 500 ms    Interactive control           ✗*   ✓
```
`*` iOS WebRTC support exists but requires a dedicated client (not AVPlayer).

## 11. Related Documents

- `docs/architecture/HLS.md` — LL-HLS streaming architecture
- `docs/architecture/ARC42.md` — System context and runtime view
- `docs/testing/webrtc-integration-checklist.md` — **Integration test checklist and runbook**
- `shared/video-protocol/UDP_Frame_Format_Documentation.md` — UDP frame protocol spec
- `docs/requirements/PRD.md` — Product requirements (FR §3, NFR §1–3)
- `docs/requirements/PROJECT_PLAN.md` — M3 milestone plan

## 12. Open Questions

- Stack decision: GStreamer `webrtcbin` vs `aiortc`? (M0-3 ADR)
- TURN server: self-hosted Coturn vs cloud (Twilio, Cloudflare)? (affects WAN cost)
- Signaling server deployment: on Pi or separate host? (affects single-Pi setup)
- Browser integration: standalone HTML demo (`M3-3`) or integrate into `clients/web/CameraView`?
