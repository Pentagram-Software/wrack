## Why

The household camera stream (`edge/video-streamer/`) has no awareness of what's in frame. The PRD ([Cat Detection and Identification V1](https://linear.app/pentagram-software/document/prd-cat-detection-and-identification-v1-640b28b7eec9)) calls for a hybrid edge-to-cloud system that detects cat appearances on the live Pi camera feed, identifies which of the three household cats (Ryfka, Chaja, Lea) it is — or `unknown` — and stores confirmed event metadata in BigQuery for later analytics and model improvement. This is V1: metadata-only, no snapshots, no alerts, optimizing for trustworthy event generation over broad recognition coverage.

**V1 ships in two internal phases**, so a working, generic "a cat was seen" signal lands end-to-end before the harder, user-specific identification problem is tackled:
- **Phase 1 — generic detection**: an off-the-shelf pretrained cat detector, wired through event confirmation, straight to BigQuery. Every event's identity is fixed to `unknown` — no per-cat model yet.
- **Phase 2 — identification**: adds per-cat identity (Ryfka, Chaja, Lea) on top of the same, already-live event pipeline, replacing the fixed `unknown` with real identification output.

## What Changes

- Add local, ONNX-based cat **detection** on the Raspberry Pi (3 FPS) — **Phase 1** — reusing `edge/video-streamer/`'s existing camera capture path rather than opening a second one.
- Add **event confirmation and lifecycle** logic — **Phase 1**: an event is only confirmed after 3 consecutive detected frames, stays active while presence continues, and ends via a configurable absence cooldown. Identity-agnostic — operates purely on detection presence/absence.
- Add **cloud emission** of confirmed cat events — **Phase 1**: one new `event_type` (`cat_detection`) and one new payload schema in `shared/telemetry-types/`, sent through the existing unified ingress and `edge/vision/telemetry/` (PEN-166) sender machinery. `final_identity` is fixed to `unknown` for every event until Phase 2 lands. No changes to `cloud/functions/ingress.js`, `bigquery-client.js`, or the `wrack_telemetry.events` table — both are already generic across event types.
- Add local cat **identification** — **Phase 2** — using a frozen embedding backbone and per-cat prototype vectors (not a closed-set classifier) enrolled from a small set of user-provided photos per cat, with a confidence threshold and `unknown` fallback. Wires into the Phase 1 event pipeline, replacing the fixed `unknown` identity with real output.
- Add fresh GCP storage infrastructure — **Phase 2** (three GCS buckets + two least-privilege service accounts) for raw per-cat photos, processed splits, and exported ONNX model artifacts. Not needed for Phase 1's off-the-shelf detector. Deliberately built clean rather than reviving prior unmerged infra branches, and trimmed of the containerized-training permissions those branches assumed (training runs locally for V1).
- All model training happens outside the deployed system (local/laptop) for V1; no cloud training infrastructure (e.g. Vertex AI Custom Jobs, Artifact Registry) is introduced.

**BREAKING**: None — this is entirely additive; no existing capability's behavior changes.

## Capabilities

### New Capabilities
- `cat-detection` (**Phase 1**): Local, on-device detection of cat presence in each sampled camera frame, producing a bounding box/crop and a detection confidence score at a configurable frame rate.
- `cat-event-lifecycle` (**Phase 1**): Turning a stream of per-frame detection results into discrete, confirmed events — requiring multi-frame confirmation before an event starts, and a configurable absence cooldown before it ends. No dependency on identification.
- `cat-event-ingestion` (**Phase 1**, extended in **Phase 2**): Emitting confirmed cat event metadata (identity, confidence scores, timestamps, model/pipeline versions) to cloud storage for analytics, reliably and without duplication. Phase 1 always reports `final_identity: unknown`; Phase 2 populates it with real identification output.
- `cat-identification` (**Phase 2**): Determining which known cat (Ryfka, Chaja, Lea) a detected cat crop most likely matches, or falling back to `unknown` when identification confidence is below a configurable threshold.

### Modified Capabilities
None — this is a new OpenSpec-tracked area of the system; no existing specs exist yet to modify.

## Impact

- **New code**: a new vision runtime under `edge/vision/` (detection + identification + pipeline orchestration), built on top of the existing `edge/vision/telemetry/` (PEN-166) event/sender machinery.
- **New schema**: `shared/telemetry-types/schemas/cat_detection.json` (new payload schema) and one new `event_type` enum entry, added to every package that independently hardcodes that enum: `shared/telemetry-types/schemas/event_envelope.json`, `shared/telemetry-types/python/events.py`, `shared/telemetry-types/typescript/events.ts`, and `edge/vision/telemetry/schemas.py` — see design.md's "Cloud ingestion" decision.
- **New infrastructure** (Phase 2 only): GCS buckets and service accounts for cat photo/model storage (fresh build, no dependency on prior unmerged branches).
- **Reused, unchanged**: `edge/video-streamer/`'s camera capture path, the unified ingress Cloud Function, `bigquery-client.js`, and the `wrack_telemetry.events` table schema — none of these require code changes. The existing `vision_detection` (PEN-169) per-frame event type is also unchanged and continues to coexist alongside the new `cat_detection` type — see design.md.
- **Out of scope for this change** (per PRD, deferred to PRD Phase 2 — a different, later phase than this change's internal Phase 2 above): recognition of non-cat animals/objects, image snapshots, alerts/notifications, human review workflows, auto-retraining, multi-camera support, and cloud-side inference on the primary runtime path.
