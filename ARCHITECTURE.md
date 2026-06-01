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
2. iOS App and Web Controller receive and decode stream

### Telemetry flow
1. EV3 sensors → Raspberry Pi vision model → BigQuery

## Component Docs

- Video protocol: [`shared/video-protocol/UDP_Frame_Format_Documentation.md`](shared/video-protocol/UDP_Frame_Format_Documentation.md)
- Video streaming architecture: [`docs/architecture/ARC42.md`](docs/architecture/ARC42.md)
- CatRecognizer IAM setup: [`docs/cat-recognizer/setup-iam.md`](docs/cat-recognizer/setup-iam.md)

## CatRecognizer ML Infrastructure

```
Edge (Raspberry Pi)
  cat-recognizer-data SA ──objectAdmin──► GCS training-data bucket
                                                    │
                                              (read-only)
                                                    ▼
  cat-recognizer-trainer SA ──────────────► Training (workstation / CI)
    ──objectAdmin──► GCS models bucket
    ──AR writer───► Artifact Registry (cat-recognizer repo, europe-west3)
```

Setup: `GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-iam.sh`  
Smoke test: `bash cloud/cat-recognizer/smoke-test.sh --mode=data`
