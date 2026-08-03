## ADDED Requirements

### Requirement: Confirmed Event Emission to Cloud
The system SHALL emit exactly one event record per confirmed cat event occurrence, at the point the event ends (not at confirmation), to the existing unified telemetry ingress as a `type=event` record, for storage in BigQuery. A cat event confirmed but not yet ended SHALL NOT produce any emission.

#### Scenario: Confirmed event is emitted once, at close
- **WHEN** a cat event is confirmed (per the event-confirmation requirement) and subsequently ends (per the absence-cooldown requirement)
- **THEN** exactly one event record is emitted to the unified ingress with `type` set to `event`, containing both the event's start time and end time

#### Scenario: Phase 1 fixes identity fields to their default values
- **WHEN** an event is emitted before per-cat identification exists (Phase 1)
- **THEN** the record's `predicted_identity` and `final_identity` are both `unknown`, and `identification_confidence` is `null` (present but unset, distinguishing "not attempted" from a real zero-confidence result)

### Requirement: Required Event Fields
Each emitted cat event record SHALL include, at minimum: event timestamp, event start time, event end time (when available), predicted identity, final identity, detection confidence, identification confidence, source device identifier, model version, pipeline version, and ingestion timestamp.

#### Scenario: Emitted event contains required fields
- **WHEN** a confirmed event record is emitted
- **THEN** the record includes event timestamp, start time, end time (if available), predicted identity, final identity, detection confidence, identification confidence, device identifier, model version, and pipeline version

### Requirement: Stable Event Identity for Deduplication
Each event occurrence SHALL be assigned one stable identifier, minted once and reused unchanged across every retry of the same occurrence, so that the shared BigQuery streaming-insert path's `insertId`-based deduplication (a best-effort window of roughly one minute, per `cloud/functions/bigquery-client.js`) can dedupe retried or redelivered sends of that occurrence. This requirement does not, by itself, guarantee zero duplicates outside that window — the target duplicate rate is the PRD §9 threshold, not "provably at most one row ever."

#### Scenario: Retried delivery within the dedupe window does not duplicate a stored event
- **WHEN** the same confirmed event occurrence is submitted more than once, within the shared BigQuery dedupe window, due to a retried or redelivered send
- **THEN** the retried sends reuse the same stable identifier as the original, and the streaming-insert path stores at most one corresponding row

### Requirement: Resilience to Transient Connectivity Issues
The system SHALL tolerate transient connectivity issues when emitting event metadata, consistent with the retry/timeout behavior already established by the shared Raspberry Pi telemetry sender.

#### Scenario: Transient network failure during emission
- **WHEN** a transient network failure occurs while emitting a confirmed event
- **THEN** the system does not crash or stop processing subsequent detections, and the event is retried or logged per the shared telemetry sender's existing behavior
