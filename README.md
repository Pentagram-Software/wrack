# Wrack — Robot Controller System

Monorepo for the Pentagram robot controller system built around the LEGO Mindstorms EV3 robot, Raspberry Pi edge computing, and a GCP cloud backend.

## System Overview

```
PS4 Controller ──bluetooth──► EV3 Robot ◄──────────────────────┐
                                                                  │
Raspberry Pi ──UDP video──► iOS App                              │
             ──UDP video──► Web Controller ──REST──► GCP Cloud ──┘
             ──vision data──► BigQuery
```

## Components

| Path | Description | Language |
|------|-------------|----------|
| `robot/controller/` | EV3 robot firmware + PS4 controller support | Python |
| `edge/video-streamer/` | UDP video streamer running on Raspberry Pi | Python |
| `edge/vision/` | Image analysis model on Raspberry Pi | Python |
| `cloud/functions/` | GCP Cloud Functions | Python |
| `cloud/bigquery/` | BigQuery schemas and migrations | SQL |
| `clients/ios/` | iPhone app — robot control + video stream | Swift |
| `clients/web/` | Web controller — robot state, video, map | TypeScript |
| `samples/python-video-receiver/` | macOS Python app for testing video stream | Python |
| `shared/video-protocol/` | UDP frame format specification + platform packages | — |

## Docs

- [Architecture](docs/architecture/system-overview.md)
- [Requirements](docs/requirements/system-requirements.md)
- [ADR](docs/adr/)

## Development

```bash
make setup        # install all dependencies
make deploy-edge  # deploy to Raspberry Pi
make deploy-cloud # deploy GCP functions
```
