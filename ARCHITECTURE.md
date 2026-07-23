# System Architecture

## Layers

```
┌─────────────────────────────────────────────────────┐
│  Clients          iOS App │ Web Controller           │
├─────────────────────────────────────────────────────┤
│  Cloud            GCP Cloud Functions │ BigQuery     │
├─────────────────────────────────────────────────────┤
│  Edge             Raspberry Pi — video streamer      │
│                              — vision model          │
├─────────────────────────────────────────────────────┤
│  Robot            EV3 — controller │ PS4/PS5 support │
└─────────────────────────────────────────────────────┘
```

## Data Flows

### Control flow
1. User acts on iOS/Web → REST call to GCP Cloud Functions
2. GCP Cloud Functions → command to EV3 robot

### Video flow
1. Camera on Raspberry Pi → UDP video stream (see `shared/video-protocol/`)
2. **iOS App**: receives and decodes UDP stream directly (Swift `VideoStreamClient`)
3. **Web browser**: cannot use raw UDP; instead:
   - `edge/ws-bridge/` runs alongside the Pi streamer (or on any reachable host)
   - Bridge registers as a UDP client, reassembles frames, and forwards them over WebSocket
   - Browser connects to the WebSocket bridge via `clients/web/src/lib/videoStream.ts`
   - H.264 frames decoded via the WebCodecs API; JPEG frames displayed via blob URL

```
Pi Camera ──H.264/JPEG UDP──► ws-bridge ──WebSocket (binary)──► Browser (WebCodecs / canvas)
```

### Telemetry flow
1. EV3 sensors → Raspberry Pi vision model → BigQuery

## Component Docs

- Video protocol: [`shared/video-protocol/UDP_Frame_Format_Documentation.md`](shared/video-protocol/UDP_Frame_Format_Documentation.md)
- Video streaming architecture: [`docs/architecture/ARC42.md`](docs/architecture/ARC42.md)
