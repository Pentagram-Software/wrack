# Project Plan (Linear-Ready)

This plan is structured for easy transfer into Linear as Projects (milestones)
with Issues (tasks) and explicit dependencies.

## Projects (Milestones)
- M0 Decisions and Setup
- M1 Capture, Encode, and Test Receiver
- M2 HLS Streaming
- M3 WebRTC Streaming
- M4 Reliability, Config, and Ops
- M5 Documentation and Handoff

## Issues (Tasks)

### M0 Decisions and Setup
- M0-1 Validate Pi 5 H.264 HW encoder path (Picamera2 + stack)
- M0-2 Choose HLS stack (LL-HLS segmenter + HTTP server)
- M0-3 Choose WebRTC stack (GStreamer webrtcbin vs aiortc)
- M0-4 Environment setup checklist and decision log

### M1 Capture, Encode, and Test Receiver
- M1-1 Implement Picamera2 capture (configurable FPS/resolution) on Pi
- M1-2 Implement H.264 encoder config (bitrate/profile/GOP) on Pi
- M1-3 Implement UDP chunking sender for encoded frames on Pi
- M1-4 Implement macOS UDP receiver (reassembly + display)
- M1-5 Log FPS/bitrate/encoder status (Pi) and receive stats (macOS)
- M1-6 Add unit tests for capture/encode config, UDP chunking, and logging

### M2 HLS Streaming
- M2-1 LL-HLS pipeline on Pi (segmenter + playlist)
- M2-2 Configure Nginx for playlists and segments
- M2-3 Validate iOS playback (AVPlayer) and browser playback
- M2-4 Validate LAN playback and latency
- M2-5 Validate WAN playback and latency
- M2-6 HLS integration test checklist and runbook

### M3 WebRTC Streaming
- M3-1 WebRTC pipeline on Pi (RTP/DTLS/SRTP)
- M3-2 Minimal signaling server
- M3-3 Browser playback client (HTML/JS)
- M3-4 Reconnect logic and basic health checks
- M3-5 WebRTC integration test checklist and runbook

### M4 Reliability, Config, and Ops
- M4-1 Config file + CLI flags
- M4-2 Health endpoint and logging improvements
- M4-3 Basic security (HTTPS/TLS for HLS, WebRTC DTLS/SRTP config)
- M4-4 Enforce unit tests in CI and review checklist

### M5 Documentation and Handoff
- M5-1 Update `docs/architecture/ARC42.md` and ADRs
- M5-2 Deployment instructions + usage examples
- M5-3 Release checklist

## Dependencies
- M1 depends on M0.
- M2 depends on M1.
- M3 can start after M1 and finalize after M2 decisions.
- M4 depends on stable M2 and M3 behavior.
- M5 depends on M4 completion.

## Linear Import (CSV Template)

Use this CSV format for Linear import. Fill in assignees and dates as needed.

```
issue_title,issue_description,project,status,priority,estimate,labels,blocked_by
M0-1 Validate H264 HW encoder path,Confirm Picamera2 + HW H.264 pipeline on Pi 5,M0 Decisions and Setup,Todo,High,3,architecture,
M0-2 Choose HLS stack,Decide LL-HLS segmenter and HTTP server (Nginx),M0 Decisions and Setup,Todo,High,2,architecture,
M0-3 Choose WebRTC stack,Decide between GStreamer webrtcbin or aiortc,M0 Decisions and Setup,Todo,Medium,2,architecture,
M0-4 Setup checklist and decision log,Document tooling setup and decisions,M0 Decisions and Setup,Todo,Medium,2,process,
M1-1 Picamera2 capture,Configurable FPS and resolution on Pi; add unit tests for new logic,M1 Capture, Encode, and Test Receiver,Todo,High,5,backend,M0-1
M1-2 H264 encoder config,Bitrate/profile/GOP settings on Pi; add unit tests for new logic,M1 Capture, Encode, and Test Receiver,Todo,High,3,backend,M1-1
M1-3 UDP chunking sender,Chunk and send encoded frames over UDP on Pi; add unit tests for new logic,M1 Capture, Encode, and Test Receiver,Todo,High,3,backend,M1-2
M1-4 macOS UDP receiver,Reassembly + display with FPS stats; add unit tests for new logic,M1 Capture, Encode, and Test Receiver,Todo,High,3,frontend,M1-3
M1-5 Metrics logging,Log encoder stats on Pi and receive stats on macOS; add unit tests for new logic,M1 Capture, Encode, and Test Receiver,Todo,Medium,2,observability,M1-4
M1-6 Unit tests for capture/encode/UDP,Add unit tests for capture/encode config, UDP chunking, and logging,M1 Capture, Encode, and Test Receiver,Todo,Medium,2,qa,M1-5
M2-1 LL-HLS pipeline,Segmenter and playlist generation on Pi; add unit tests for new logic,M2 HLS Streaming,Todo,High,5,streaming,M1-2
M2-2 Nginx HLS serving,Serve playlists and segments via Nginx; add unit tests for config validation where applicable,M2 HLS Streaming,Todo,High,3,ops,M2-1
M2-3 iOS + web playback,Validate AVPlayer and browser playback; add unit tests for any playback tooling,M2 HLS Streaming,Todo,High,3,frontend,M2-2
M2-4 LAN validation,Validate LAN playback and latency,M2 HLS Streaming,Todo,Medium,2,qa,M2-3
M2-5 WAN validation,Validate WAN playback and latency,M2 HLS Streaming,Todo,Medium,2,qa,M2-4
M2-6 HLS integration checklist,Define integration test checklist and runbook for HLS playback,M2 HLS Streaming,Todo,Medium,2,qa,M2-5
M3-1 WebRTC pipeline,RTP + SRTP/DTLS pipeline on Pi; add unit tests for new logic,M3 WebRTC Streaming,Todo,High,5,streaming,M1-2
M3-2 Signaling server,Minimal signaling for browser client; add unit tests for new logic,M3 WebRTC Streaming,Todo,High,3,backend,M3-1
M3-3 Browser client,Basic HTML/JS playback; add unit tests for new logic,M3 WebRTC Streaming,Todo,High,3,frontend,M3-2
M3-4 Reconnect and health,Reconnect logic + health checks; add unit tests for new logic,M3 WebRTC Streaming,Todo,Medium,2,observability,M3-3
M3-5 WebRTC integration checklist,Define integration test checklist and runbook for WebRTC playback,M3 WebRTC Streaming,Todo,Medium,2,qa,M3-4
M4-1 Config + CLI,Single config file and flags; add unit tests for new logic,M4 Reliability, Config, and Ops,Todo,High,3,ops,M2-5;M3-4
M4-2 Health + logging,Health endpoint and improved logs; add unit tests for new logic,M4 Reliability, Config, and Ops,Todo,Medium,2,ops,M4-1
M4-3 Basic security,HTTPS/TLS for HLS + WebRTC security config; add unit tests for new logic,M4 Reliability, Config, and Ops,Todo,High,3,security,M4-2
M4-4 Unit test enforcement,Add CI gate and review checklist requiring unit tests for dev tickets,M4 Reliability, Config, and Ops,Todo,Medium,2,process,
M5-1 Update ARC42 and ADRs,Architecture docs update,M5 Documentation and Handoff,Todo,Medium,2,docs,M4-3
M5-2 Deployment docs,Setup and usage examples,M5 Documentation and Handoff,Todo,Medium,2,docs,M5-1
M5-3 Release checklist,Final release readiness list,M5 Documentation and Handoff,Todo,Low,1,process,M5-2
```
