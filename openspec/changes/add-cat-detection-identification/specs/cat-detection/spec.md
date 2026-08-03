## ADDED Requirements

### Requirement: Local On-Device Detection
The system SHALL run cat detection locally on the Raspberry Pi. Cloud-side inference SHALL NOT be part of the primary detection path.

#### Scenario: Detection runs without a network dependency
- **WHEN** the Pi's network connection is unavailable
- **THEN** cat detection continues to run and produce per-frame results using only on-device inference

### Requirement: Configurable Sampled Frame Rate
The system SHALL evaluate camera frames for cat presence at a configurable rate, defaulting to 3 FPS.

#### Scenario: Frames are evaluated at the configured rate
- **WHEN** the detection pipeline is running with the default configuration
- **THEN** frames are sampled and evaluated at approximately 3 frames per second

### Requirement: Shared Camera Capture Path
The system SHALL consume camera frames from the same capture path already used by `edge/video-streamer/`, rather than opening an independent camera session.

#### Scenario: Detection and streaming run concurrently
- **WHEN** the video streamer is actively streaming and the detection pipeline is running
- **THEN** both consume frames from a single shared capture path without duplicating camera decode/encode work

### Requirement: Per-Frame Detection Confidence
Each evaluated frame SHALL produce at most one detection result, consisting of a presence/absence outcome, a confidence score, and (when a cat is present) a crop or bounding box suitable for downstream identification. When the underlying detector reports multiple candidate cat regions in the same frame, the system SHALL keep only the single highest-confidence one and discard the rest — V1 does not track or report multiple simultaneous cats.

#### Scenario: Cat present in frame
- **WHEN** an evaluated frame contains a visible cat
- **THEN** the detection result indicates presence with a confidence score and a crop of the detected region

#### Scenario: No cat present in frame
- **WHEN** an evaluated frame contains no cat
- **THEN** the detection result indicates absence, and no crop is produced

#### Scenario: Multiple cats present in the same frame
- **WHEN** an evaluated frame contains more than one candidate cat region
- **THEN** the detection result reflects only the highest-confidence region; the other candidate regions are discarded and do not produce separate detection results or events
