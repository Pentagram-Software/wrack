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
│  Robot            EV3 — controller │ PS4 support     │
└─────────────────────────────────────────────────────┘
```

## Data Flows

### Control flow
1. User acts on iOS/Web → REST call to GCP Cloud Functions
2. GCP Cloud Functions → command to EV3 robot

### Video flow
1. Camera on Raspberry Pi → UDP video stream (see `shared/video-protocol/`)
2. iOS App and Web Controller receive and decode stream

### Telemetry flow
1. EV3 sensors → Raspberry Pi vision model → BigQuery

## Component Docs

- Video protocol: [`shared/video-protocol/UDP_Frame_Format_Documentation.md`](shared/video-protocol/UDP_Frame_Format_Documentation.md)
- Video streaming architecture: [`docs/architecture/ARC42.md`](docs/architecture/ARC42.md)
