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

Three-bucket layout (PEN-25):

```
Edge (Raspberry Pi)
  cat-recognizer-data SA
    ──objectAdmin──►  GCS raw-data bucket  (<proj>-cat-recognizer-raw-data)
                         ryfka/ │ chaja/ │ lea/   (90-day auto-delete)
    ──objectViewer──► GCS processed-data bucket

                                    │ (objectViewer — read raw frames)
                                    ▼
  cat-recognizer-trainer SA ─────────────────────► Training (workstation / CI)
    ──objectAdmin──►  GCS processed-data bucket (<proj>-cat-recognizer-processed-data)
                         train/ │ val/ │ test/
    ──objectAdmin──►  GCS models bucket         (<proj>-cat-recognizer-models)
    ──AR writer───►   Artifact Registry (cat-recognizer repo, europe-west3)
```

Setup: `GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-iam.sh`  
Smoke test: `bash cloud/cat-recognizer/smoke-test.sh --mode=data`
