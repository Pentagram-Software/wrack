# Phase 1 — Generic Cat Detection (no per-cat identity)

## 1. Detection

- [ ] 1.1 Select 1-2 candidate pretrained, COCO-class ONNX object detectors and filter to the "cat" class <!-- linear:PEN-238 -->
- [ ] 1.2 Benchmark each candidate on the Pi 5 (FPS, CPU%, memory, thermal) while the video streamer is also running, per `edge/vision/README.md`'s Phase 1 milestone <!-- linear:PEN-239 -->
- [ ] 1.3 Pick the detector to move forward with, based on the benchmark <!-- linear:PEN-240 -->
- [ ] 1.4 Wire the detector into a Pi-side inference loop reading frames from `edge/video-streamer/`'s existing capture path, at a configurable FPS (default 3) — parallel impl in PR #108 (not merged; leave unchecked until on main): inference loop machinery written (`pipeline.py`), but the actual tap into `edge/video-streamer/`'s live capture path is not wired up; see `pipeline.py`'s module docstring <!-- linear:PEN-241 -->
- [ ] 1.5 Produce, per evaluated frame, a detection result (presence/absence, confidence, crop when present) <!-- linear:PEN-242 -->

## 2. Event Lifecycle

- [ ] 2.1 Implement 3-consecutive-frame event confirmation (no event on isolated/unconfirmed single-frame detections) <!-- linear:PEN-243 -->
- [ ] 2.2 Implement active-event state that persists while cat presence continues <!-- linear:PEN-244 -->
- [ ] 2.3 Implement the configurable absence cooldown that ends an event and allows a new one to start <!-- linear:PEN-245 -->
- [ ] 2.4 Make FPS, confirmation frame count, cooldown duration, and detection confidence threshold externally configurable (not hardcoded), per PRD §8 / §12 — the identity confidence threshold (a separate knob) is covered by task 6.5 <!-- linear:PEN-246 -->

## 3. Cloud Ingestion

- [ ] 3.1 Add a `cat_detection` entry to the `event_type` enum everywhere it's independently hardcoded: `shared/telemetry-types/schemas/event_envelope.json` (JSON Schema), `shared/telemetry-types/python/events.py` (`VALID_EVENT_TYPES`), `shared/telemetry-types/typescript/events.ts` (`EventType`), and `edge/vision/telemetry/schemas.py` (`VALID_EVENT_TYPES`) — plus matching test updates for each; `cloud/functions/telemetry.js`'s `validateEvent()` is loose on enum today so needs no change, but the shared/edge validators are strict and will reject the event otherwise even if the cloud ingress accepts it <!-- linear:PEN-247 -->
- [ ] 3.2 Create `shared/telemetry-types/schemas/cat_detection.json` covering the required fields (timestamps, predicted/final identity, detection/identification confidence, device_id, model_version, pipeline_version); Phase 1 always emits the full default tuple `predicted_identity: "unknown"`, `final_identity: "unknown"`, `identification_confidence: null` (per the cat-event-ingestion spec's "Phase 1 fixes identity fields to their default values" scenario) since no identification model is wired in yet — `identification_confidence` must be nullable, not required-non-null, and `predicted_identity` must not be left unspecified <!-- linear:PEN-248 -->
- [ ] 3.3 Wire confirmed-event emission through `edge/vision/telemetry/`'s existing event/sender machinery, tagged `type=event` <!-- linear:PEN-249 -->
- [ ] 3.4 Verify a retried/redelivered send of the same event occurrence reuses the same stable identifier and is deduplicated by the shared BigQuery streaming-insert path's `insertId` window (~1 minute, per `cloud/functions/bigquery-client.js`) — this is the existing infrastructure's guarantee, not a new stronger dedupe mechanism <!-- linear:PEN-250 -->
- [ ] 3.5 Run an end-to-end test: a confirmed event on the Pi results in exactly one row in `wrack_telemetry.events` with `final_identity: "unknown"` and the expected fields — parallel impl in PR #108 (not merged; leave unchecked until on main): script written (`validation/e2e_ingestion_test.py`), not run (needs real Pi + deployed ingress + device token) <!-- linear:PEN-251 -->

## 4. Phase 1 Integration Validation

- [ ] 4.1 Run the Phase 1 pipeline (streamer + detection + event lifecycle + ingestion) on the Pi for an extended soak period and confirm no manual restarts are needed — parallel impl in PR #108 (not merged; leave unchecked until on main): harness written (`validation/soak_test.py`), not run <!-- linear:PEN-252 -->
- [ ] 4.2 Spot-check false positive rate against the PRD §9 detection target, using real household observation <!-- linear:PEN-253 -->
- [ ] 4.3 Confirm CPU/memory/thermal stay within acceptable bounds with the Phase 1 pipeline running <!-- linear:PEN-254 -->

# Phase 2 — Identification (Ryfka / Chaja / Lea)

## 5. GCP Infrastructure

- [ ] 5.1 Create the three GCS buckets (`<project>-cat-recognizer-raw-data`, `-processed-data`, `-models`) with the `raw-data` bucket's 90-day lifecycle rule — parallel impl in PR #108 (not merged; leave unchecked until on main): scripted in `cloud/cat-recognizer/setup-infra.sh`, not run against real GCP <!-- linear:PEN-255 -->
- [ ] 5.2 Create the `raw-data/{ryfka,chaja,lea}/` and `processed-data/{train,val,test}/` folder structure — parallel impl in PR #108 (not merged; leave unchecked until on main): scripted in `cloud/cat-recognizer/setup-infra.sh`, not run <!-- linear:PEN-256 -->
- [ ] 5.3 Create two least-privilege service accounts (data-collector, trainer/export) with bucket-scoped IAM roles only — no Artifact Registry roles — parallel impl in PR #108 (not merged; leave unchecked until on main): scripted in `cloud/cat-recognizer/setup-infra.sh`, not run <!-- linear:PEN-257 -->
- [ ] 5.4 Write a smoke test verifying each service account's expected read/write access per bucket — parallel impl in PR #108 (not merged; leave unchecked until on main): written (`cloud/cat-recognizer/smoke_test.py`), not run (depends on 5.1-5.3) <!-- linear:PEN-258 -->
- [ ] 5.5 Document the infra (README + IAM runbook), noting explicitly that this supersedes the unmerged `cursor/pen-24`/`cursor/pen-25` branches rather than building on them <!-- linear:PEN-259 -->

## 6. Identification

- [ ] 6.1 Select a CPU-friendly, pretrained embedding backbone suitable for ARM64/ONNX Runtime <!-- linear:PEN-260 -->
- [ ] 6.2 Benchmark the selected embedding backbone on the Pi 5 (per-crop inference latency, CPU%, memory), standalone and with the video streamer running, mirroring the detector benchmark in 1.2 — parallel impl in PR #108 (not merged; leave unchecked until on main): script written (`identification/benchmark.py`), not run <!-- linear:PEN-261 -->
- [ ] 6.3 Build an enrollment script/tool that takes a cat's reference photos and produces an averaged prototype embedding <!-- linear:PEN-262 -->
- [ ] 6.4 Enroll Ryfka, Chaja, and Lea from the user's existing iPhone photos (15-50 per cat) — parallel impl in PR #108 (not merged; leave unchecked until on main): tool written (`identification/enroll.py`), needs real photos this session doesn't have access to <!-- linear:PEN-263 -->
- [ ] 6.5 Implement distance-based identification (compare a detected crop's embedding to all enrolled prototypes) with a configurable confidence threshold <!-- linear:PEN-264 -->
- [ ] 6.6 Implement the `unknown` fallback (final identity `unknown` below threshold, while still recording the top predicted identity) <!-- linear:PEN-265 -->
- [ ] 6.7 Wire the identification backbone into the Pi-side inference loop, consuming detection crops from 1.4/1.5 and producing a per-frame identification result <!-- linear:PEN-266 -->
- [ ] 6.8 Do a first-pass threshold sanity check using held-out enrollment photos (explicitly provisional — see design.md's open question on threshold validation) — parallel impl in PR #108 (not merged; leave unchecked until on main): script written (`identification/evaluate_threshold.py`), needs real photos <!-- linear:PEN-267 -->

## 7. Wire Real Identity into the Event Pipeline

- [ ] 7.1 Replace the Phase 1 fixed `final_identity: "unknown"` with the real predicted/final identity and identification confidence from section 6, in the emitted event payload <!-- linear:PEN-268 -->
- [ ] 7.2 Re-run the end-to-end ingestion test (3.5) confirming real identity values land correctly in `wrack_telemetry.events` — parallel impl in PR #108 (not merged; leave unchecked until on main): reuses `validation/e2e_ingestion_test.py`, not run <!-- linear:PEN-269 -->

## 8. Phase 2 Integration Validation

- [ ] 8.1 Run the full pipeline (streamer + detection + identification + event lifecycle + ingestion) on the Pi for an extended soak period and confirm no manual restarts are needed — parallel impl in PR #108 (not merged; leave unchecked until on main): reuses `validation/soak_test.py` with `--embedding-model`/`--prototypes`, not run <!-- linear:PEN-270 -->
- [ ] 8.2 Spot-check known-cat identification accuracy against the PRD §9 targets, using real household observation <!-- linear:PEN-271 -->
- [ ] 8.3 Confirm CPU/memory/thermal stay within acceptable bounds with the full pipeline running (not just the detector benchmark from 1.2 or the identifier benchmark from 6.2) <!-- linear:PEN-272 -->

# Follow-on: Bootstrap Domain-Gap Closing (not required to ship V1, but designed for)

## 9. Domain-Gap Bootstrap

- [ ] 9.1 From live Pi detections, collect a small number of real camera-domain crops per known cat <!-- linear:PEN-273 -->
- [ ] 9.2 Hand-label those crops with the correct identity <!-- linear:PEN-274 -->
- [ ] 9.3 Enrich each cat's prototype with the labeled camera-domain crops, alongside the original iPhone photos <!-- linear:PEN-275 -->
- [ ] 9.4 Re-check identification accuracy after enrichment <!-- linear:PEN-276 -->
