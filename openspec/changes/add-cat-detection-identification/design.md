## Context

`edge/video-streamer/` already runs continuously on the Raspberry Pi 5, streaming H.264 over UDP. Measured on the actual device: idle CPU/memory are <1% (47°C); with the streamer running (Pi 5 has no hardware H.264 encoder block, so this is software encoding via `LibavH264Encoder`), CPU rises to ~9.5%, memory to ~10%, temperature to ~50°C. There is comfortable headroom for additional on-device inference, though the real number (with a detector and identifier both running at 3 FPS) hasn't been benchmarked yet — `edge/vision/README.md`'s own Phase 1 milestone ("hardware benchmark: 1-2 ONNX detectors on Pi 5 → FPS/CPU/thermal table") remains the way to get that number once a candidate model exists.

The telemetry transport layer already exists and is generic: `edge/vision/telemetry/` (PEN-166) builds and sends event envelopes from the Pi; the unified ingress Cloud Function (`cloud/functions/ingress.js`, PEN-227) routes `type=event` records to `bigquery-client.js`'s `insertEvents()`, which inserts into `wrack_telemetry.events` — a single table with a generic `JSON` `payload` column, partitioned by day and clustered by `(source, event_type)`. None of this requires modification to support a new event type.

That same `edge/vision/telemetry/` module already defines a per-frame `vision_detection` event type (builder, payload validator, and tests, under PEN-169) — see the "cat_detection coexists with vision_detection" decision below for how the two relate.

A prior planning pass (now archived in Linear) picked Vertex AI Custom Jobs for training and TFLite for the model format, and left unmerged, mutually-diverged GCP infra branches (`cursor/pen-24-gcp-iam-service-accounts-cc54`, `cursor/pen-25-infra-provision-gcs-buckets-{44a6,f9ef}`). Those decisions are superseded by this design: training is local/laptop-side for V1, and the model format is ONNX (matching `edge/vision/README.md`'s existing recommendation). The infra those branches built is not reused directly, though their three-bucket shape is a useful reference.

Only 15-50 photos per cat are available for identification (the user's own iPhone photos of Ryfka, Chaja, and Lea) — no public dataset covers these specific individuals. This is a hard constraint that shapes the identification design below.

## Goals / Non-Goals

**Goals:**
- Detect cat presence on the live Pi camera feed at 3 FPS using a pretrained, ONNX-exported detector, without duplicating `edge/video-streamer/`'s camera capture path.
- Identify a detected cat as Ryfka, Chaja, Lea, or `unknown`, using an approach that works with only 15-50 enrollment photos per cat and doesn't require full retraining to add a future identity.
- Confirm events using a 3-consecutive-frame rule and manage event start/end via a configurable absence cooldown.
- Emit confirmed event metadata to BigQuery via the existing ingestion path, reliably and without duplication.
- Provide fresh, least-privilege GCP storage infrastructure for raw photos, processed splits, and exported model artifacts.

**Non-Goals:**
- Training infrastructure in the cloud (Vertex AI, Artifact Registry, containerized training jobs) — V1 trains locally.
- Recognition of non-cat animals/objects, snapshots, alerts, human review workflows, auto-retraining, or multi-camera support (all explicitly deferred to PRD Phase 2).
- Closing the iPhone-photo-to-Pi-camera domain gap within this change — that's a follow-on bootstrap step once the detector is live and can supply real camera-domain crops, not a V1 blocker.
- Picking a specific detector architecture or embedding backbone in this document — those are implementation decisions made during the benchmark/prototyping tasks, not architectural commitments this design needs to lock in.
- Tracking or reporting multiple simultaneous cats in one frame — when more than one is detected, only the single highest-confidence region is kept (see the cat-detection spec's "Per-Frame Detection Confidence" requirement); this also bounds what feeds into Phase 2 identification, since only that one crop is embedded and compared to prototypes.

## Decisions

### V1 ships in two internal phases: detection-only, then identification
**Decision**: Phase 1 delivers generic cat-presence detection — an off-the-shelf pretrained detector, event confirmation/lifecycle, and cloud emission with `final_identity` fixed to `unknown` — as a complete, independently shippable slice. Phase 2 adds identification on top of the same, already-live event pipeline, replacing the fixed `unknown` with real per-cat identity.

**Why**: detection and identification carry very different risk profiles. Detection uses an off-the-shelf pretrained model with no user-specific data or training required — it can be selected, benchmarked on the Pi, and shipped quickly. Identification depends on a hard, user-specific constraint (15-50 iPhone photos per cat, no public dataset) and its own open questions (threshold validation, domain gap — see Risks below). Shipping Phase 1 first gets a real, useful "a cat was seen" signal into BigQuery early, validates the Pi's compute headroom with a live pipeline (not just a benchmark), and de-risks the event/ingestion path before identification's harder problem is layered on. It also means Phase 2 touches the event/ingestion path exactly once more (swapping a fixed value for real output) rather than that path being built twice from scratch.

**Consequence**: the GCS storage infrastructure (raw photos, processed splits, model artifacts) is scoped to Phase 2 only — Phase 1's detector needs no cloud storage since it uses a pretrained model directly, with no enrollment or training data of its own.

### Detection and identification are two independent models, not one
A single model that both localizes and identifies would need retraining (or at least a new output head) every time an identity is added, and would conflate a generic, richly-supported problem (cat detection — pretrained COCO-class detectors already solve this) with a narrow, personal one (identifying 3 specific cats from a handful of photos). Keeping them separate lets detection start from an off-the-shelf pretrained model with little or no training, while identification evolves independently as more reference photos accumulate.

### Identification uses embeddings + per-cat prototypes, not a closed-set classifier
**Decision**: extract a feature vector (embedding) from each detected cat crop using a frozen, CPU-friendly pretrained backbone; compare it by distance (cosine/L2) against a stored prototype vector per known cat (the average embedding of that cat's enrollment photos); the closest prototype under a confidence threshold determines identity, otherwise `unknown`.

**Why over a closed-set softmax classifier**: with only 15-50 images per class, a trained classifier head risks overfitting to incidental correlates in the small sample (background, lighting, the specific photos taken) rather than learning identity-discriminative features. The embedding/prototype approach leans on transfer learning from the (much larger) data the backbone was originally pretrained on, and needs no training loop at all for V1 — enrollment is just a forward pass plus an average. It also directly implements the PRD's §7.4 threshold/`unknown`-fallback semantics as a natural distance cutoff, and makes adding a future identity "append a prototype" rather than "retrain a classifier head."

**Alternative considered**: closed-set 4-way classifier (ryfka/chaja/lea/unknown). Rejected for V1 given the sample size, but not ruled out permanently — if the embedding approach's accuracy proves insufficient once enough real data accumulates, a classifier becomes viable later without changing anything upstream (detection) or downstream (event lifecycle/ingestion).

### Training happens locally, not in the cloud, for V1
**Decision**: the detector likely needs evaluation/export/quantization only (starting from a pretrained COCO-class model); the identifier needs no training loop at all (embeddings + averaging). Any fine-tuning that does prove necessary is small enough to run on a laptop.

**Why over Vertex AI Custom Jobs** (the prior, now-superseded plan): that infrastructure is built for containerized, larger-scale training jobs — overkill for a problem this small, and it comes with ongoing IAM/Artifact Registry surface area to maintain for no benefit at this stage. If training needs outgrow a laptop later (e.g., a real detector fine-tune on a larger collected dataset), cloud training compute can be reintroduced without disrupting the storage layer, which is designed independently of where training runs.

### GCP infrastructure is rebuilt clean, not resurrected from prior branches
**Decision**: build a new three-bucket GCS layout — `<project>-cat-recognizer-raw-data/{ryfka,chaja,lea}/` (90-day lifecycle), `<project>-cat-recognizer-processed-data/{train,val,test}/`, `<project>-cat-recognizer-models/` (ONNX artifacts) — with two least-privilege service accounts (data-collector, trainer/export). The trainer SA does not get Artifact Registry roles, since there's no containerized training to authorize.

**Why over reviving `cursor/pen-24`/`cursor/pen-25`**: those branches diverged from each other (two independent attempts at the same ticket), were never merged, and are scoped for a training approach (Vertex AI Custom Jobs, Docker images via Artifact Registry) this design explicitly does not use. Reconciling two diverged branches and then stripping unneeded permissions is more work than writing the trimmed version directly. Their three-bucket shape remains a useful reference, not a resurrection target.

### `cat_detection` coexists with `vision_detection` (PEN-169), it does not replace it
**Decision**: `vision_detection` (PEN-169) remains the per-frame, raw telemetry contract — one record per evaluated frame, whatever the pipeline observes, with no notion of a confirmed occurrence. `cat_detection` (this change) is a separate, higher-level event type: one record per confirmed-and-closed cat *event* (a discrete household occurrence, per the cat-event-lifecycle spec), not per frame. The two contracts are independent and compatible — neither is deprecated, superseded, or left half-implemented by the other — but **this change only adds `cat_detection` emission**; it does not wire `vision_detection` emission into the new inference loop. Emitting `vision_detection` from that loop remains PEN-169's own scope, to be wired separately if and when that's wanted — no task in this change's `tasks.md` does it, and none should be inferred from this decision.

**Why**: the two serve different consumers. `vision_detection`'s raw per-frame record is the right shape for debugging the detector itself (every frame it looked at, what it saw, at what latency) — collapsing that into confirmed events would lose exactly the frame-level detail PEN-169 exists to capture. `cat_detection`'s confirmed-occurrence record is the right shape for analytics ("how many times was a cat seen today") — passing raw per-frame noise through to that use case would flood BigQuery with far more rows than any query needs, and reintroduce the false-positive risk the 3-consecutive-frame confirmation requirement exists to filter out. Neither event type depends on the other; a consumer that only cares about confirmed occurrences can safely ignore `vision_detection` entirely, and vice versa. Deferring `vision_detection` wiring keeps this change scoped to what it actually implements, rather than committing to work tracked (or not yet tracked) elsewhere.

### Cloud ingestion reuses the existing generic pipeline unchanged
**Decision**: add one `event_type` enum value (`cat_detection`) and one new payload schema (`shared/telemetry-types/schemas/cat_detection.json` covering the PRD §7.6 fields), across every package that independently hardcodes the `event_type` enum surface: `shared/telemetry-types/schemas/event_envelope.json` (JSON Schema), `shared/telemetry-types/python/events.py` (`VALID_EVENT_TYPES`), `shared/telemetry-types/typescript/events.ts` (`EventType`), and `edge/vision/telemetry/schemas.py` (`VALID_EVENT_TYPES`, RPi-specific). No changes to `cloud/functions/ingress.js`, `bigquery-client.js`, or `cloud/bigquery/schemas/events.sql` — `cloud/functions/telemetry.js`'s `validateEvent()` only checks `event_type` is a non-empty string, no enum restriction there.

**Why**: `insertEvents()` and the `events` table are already fully generic across event types (JSON `payload` column, no per-type branching) — this is the same mechanism `video_stream_start`/`stop`/`health` already use. Building anything new here would duplicate working infrastructure. Per `docs/monitoring/scope-boundary.md`'s decision table, cat events are unambiguously Wrack Analytics (trend/historical value, not sub-second health/paging signals), so the existing `type=event` → BigQuery path is the correct destination, not the Grafana/health leg.

**Emission cardinality**: exactly one event record per confirmed cat event occurrence, emitted once at the point the event ends (not a separate row at confirmation and another at close) — the record carries both the start time (from confirmation) and the end time together. A cat event that is confirmed but has not yet ended produces no emission.

### Retention: accept the existing 90-day table-wide expiration
`wrack_telemetry.events` has `partition_expiration_days=90` set once, for the whole table — not configurable per `event_type`. The user confirmed 90 days is acceptable for cat events, so no special-casing (raising the table-wide expiration, or exporting cat events elsewhere before they age out) is needed for V1.

### Pi-side capture path is shared with the video streamer
**Decision**: the detection/identification pipeline reads frames from the same capture path `edge/video-streamer/` already uses, rather than opening a second camera session.

**Why**: `edge/vision/README.md` already calls this out as the integration point to get right ("prefer a single capture path... to avoid duplicate decode/encode load"), and duplicate capture would compound exactly the CPU/thermal risk this design is otherwise trying to stay comfortably under.

## Risks / Trade-offs

- **[Domain gap]** Enrollment photos are iPhone photos (close-up, good light, phone sensor); inference-time crops come from a fixed Pi camera (wider FOV, smaller crops, home lighting, motion blur). This could make same-cat distances and different-cat distances less separable than enrollment-only validation would suggest. → **Mitigation** (explicitly out of scope for this change, but designed to be possible without rework): once the detector is live, use its real camera-domain crops to enrich each cat's prototype with in-distribution examples. The embedding/prototype design supports this incrementally — no retraining required, just adding more images to the average.
- **[Threshold validation with little data]** 15-50 photos per cat leaves little room to hold out a validation set for tuning the identity confidence threshold, and there's no confirmed source of "known unknown" photos (an unfamiliar cat) to validate the fallback path against. → **Mitigation**: treat the initial threshold as provisional and expect to retune it once the system is observing real household conditions; this is explicitly called out as an open question below rather than silently resolved.
- **[Compute headroom is estimated, not measured under load]** The 9.5% CPU / 50°C numbers are streamer-only; detector + identifier running concurrently at 3 FPS hasn't been measured. → **Mitigation**: the benchmark task (Phase 1) runs before any model is committed to, specifically to catch this before it becomes a production surprise.
- **[Diverged prior infra branches still exist unmerged]** `cursor/pen-24`/`cursor/pen-25` branches remain in the repo, unmerged, representing a different (superseded) design. → **Mitigation**: this design deliberately does not build on them; they should eventually be closed out (not silently left to rot) but doing so is not a blocker for this change.

## Migration Plan

Purely additive — no existing runtime behavior changes, no data migration, no rollback complexity beyond "don't deploy the new Pi-side pipeline / don't add the new event type." Rollout is explicitly two-phased (see `tasks.md`):
- **Phase 1**: Detection → Event Lifecycle → Cloud Ingestion (`final_identity: unknown`) → Phase 1 Integration Validation. Independently shippable — a complete, useful slice on its own.
- **Phase 2**: GCP Infrastructure → Identification → wiring real identity into the existing event pipeline → Phase 2 Integration Validation.

Each phase is reversible by not proceeding to the next; Phase 2 does not require re-deploying or restructuring anything Phase 1 shipped.

## Open Questions

- Exact detector architecture (deferred until the Pi hardware benchmark produces real FPS/CPU/thermal numbers for candidate ONNX models).
- Exact embedding backbone for identification.
- How to validate/tune the identity confidence threshold given the small, hard-to-split enrollment set.
- Precise scope of "expand further" beyond the domain-gap bootstrap — more cats, other animals (PRD Phase 2), or both — not yet decided by the user.
