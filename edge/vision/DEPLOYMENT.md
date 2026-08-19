# Deploying `edge/vision/` to the Raspberry Pi (add-cat-detection-identification)

Step-by-step prerequisites for getting the cat detection/identification pipeline actually
running, from "nothing exists yet" to a live Pi. Every script referenced here was written but
**not executed** by the `/opsx:apply` session that built this code — it had no network path to
the Pi (`raspberrypi.local` doesn't resolve from the dev machine) and no access to real cat
photos, so each step below is marked with what's been verified vs. what still needs a human to
actually run it.

Also see `../../openspec/changes/add-cat-detection-identification/tasks.md` for how these steps
map to tracked tasks, and `README.md` for the wider `edge/vision/` architecture.

## Overview

```
Dev machine (laptop)                          Raspberry Pi 5
─────────────────────                         ───────────────
1. Export detector(s) to ONNX      ──copy──►   2. Benchmark detector(s)      (task 1.2)
   (detection/export_model.py)                    (detection/benchmark.py)
                                                3. Pick a detector             (task 1.3)
                                                4. Install runtime deps        (below)
5. Export embedding backbone       ──copy──►   6. Benchmark backbone         (task 6.2)
   (identification/export_model.py)               (identification/benchmark.py)
7. Enroll cats from iPhone photos              8. Threshold sanity check     (task 6.8)
   (identification/enroll.py)     ──copy──►       (identification/evaluate_threshold.py)
                                                9. Configure telemetry env vars (below)
                                                10. Run (soak test, then production)
```

Steps 1-7 (export, enrollment) run on a laptop — none of this needs the Pi's limited compute,
and `design.md`'s "Training happens locally, not in the cloud, for V1" decision explicitly
keeps heavy ML tooling (torch, ultralytics) off deployed Pi hardware.

## 1. Export the detector(s) — dev machine

```bash
cd edge/vision
pip install -r requirements-export.txt   # ultralytics, torch, torchvision — NOT on the Pi
python3 detection/export_model.py --candidate yolov8n --imgsz 640 --output-dir exported_models/
python3 detection/export_model.py --candidate yolov5n --imgsz 640 --output-dir exported_models/
```

Produces `exported_models/yolov8n_640.onnx` and `exported_models/yolov5n_640.onnx`. See
`detection/MODEL_SELECTION.md` for why these two candidates. **Not run this session** — no
`ultralytics` install here, and the export itself downloads pretrained weights from the network.

## 2. Copy to the Pi and benchmark — Pi 5 (task 1.2)

```bash
scp exported_models/*.onnx pi@raspberrypi.local:~/cat-recognizer/models/
ssh pi@raspberrypi.local
cd ~/cat-recognizer  # wherever edge/vision/ is deployed (make deploy-edge)
python3 detection/benchmark.py --model models/yolov8n_640.onnx --decoder yolov8 --iterations 200
# yolov5n.onnx is decoded with --decoder yolov8 too — the ultralytics package's yolov5n.pt is
# YOLOv5u (anchor-free v8-style head), not the classic YOLOv5 [1, N, 85] head; see
# detection/MODEL_SELECTION.md's "Candidate B" note.
python3 detection/benchmark.py --model models/yolov5n_640.onnx --decoder yolov8 --iterations 200
# Run edge/video-streamer/ concurrently in another terminal first, then repeat with
# --concurrent-streamer to note that in the report — see benchmark.py's own docstring.
```

## 3. Pick a detector (task 1.3)

Compare the two JSON reports' `fps_estimate`, `cpu_percent_mean`, `cpu_temp_c_max`. No script
for this step — it's a judgment call based on real numbers, not something to automate.

## 4. Install Pi runtime dependencies (before or alongside steps 2-3)

```bash
sudo apt install libatlas-base-dev libjpeg-dev libopenjp2-7   # common opencv-python ARM64 gotchas
pip install -r edge/vision/requirements.txt   # onnxruntime, numpy, opencv-python, psutil
```

If `edge/video-streamer/` is already deployed and running on this Pi, the `opencv-python` system
deps are very likely already installed — only `onnxruntime` (verified: ships a prebuilt
`manylinux_2_17_aarch64` wheel, no on-device compiling needed) is new.

**Known gap**: there is no production frame source wired to the Pi's CSI camera yet.
`pipeline.py`'s `frame_source` is a deliberately pluggable seam (see its module docstring) —
`edge/video-streamer/streamer.py` was not modified to expose raw frames alongside its H.264
encoder, since that's a change to already-working production streaming code this session
couldn't test on real hardware. `validation/soak_test.py`'s `--video-source` works against a
recorded video file or a USB webcam via `cv2.VideoCapture`, but **not** reliably against the Pi's
CSI camera module the way `picamera2` does — wiring the real shared capture path is follow-up
work, not yet done.

## 5. Export the embedding backbone — dev machine (Phase 2 only, task 6.1/6.2)

```bash
python3 identification/export_model.py --output exported_models/mobilenet_v3_small_embed.onnx
scp exported_models/mobilenet_v3_small_embed.onnx pi@raspberrypi.local:~/cat-recognizer/models/
```

## 6. Benchmark the backbone — Pi 5 (task 6.2)

```bash
python3 identification/benchmark.py --model models/mobilenet_v3_small_embed.onnx --iterations 200
```

Per `design.md`'s "Compute headroom is estimated, not measured under load" risk, run this
*concurrently* with `detection/benchmark.py` (two terminals) for a number close to the real
Phase 2 combined cost, not each model in isolation.

## 7. Enroll the cats — dev machine (task 6.3/6.4)

Needs 15-50 iPhone photos per cat. **Not done this session** — no access to those photos.

```bash
mkdir -p photos/{ryfka,chaja,lea}   # drop each cat's photos into its folder
python3 identification/enroll.py --model exported_models/mobilenet_v3_small_embed.onnx \
    --photos-dir photos/ --output prototypes.json
scp prototypes.json pi@raspberrypi.local:~/cat-recognizer/
```

Hold back 3-5 photos per cat *before* running this, into a separate `held-out/` directory with
the same layout, for step 8.

## 8. Threshold sanity check — Pi or dev machine (task 6.8, provisional)

```bash
python3 identification/evaluate_threshold.py --model exported_models/mobilenet_v3_small_embed.onnx \
    --prototypes prototypes.json --held-out-dir held-out/
```

Prints a threshold sweep table — pick a starting `confidence_threshold` for `CatIdentifier` from
it. Explicitly provisional; see `design.md`'s open question on threshold validation.

## 9. Configure telemetry environment variables (before any cloud-emitting run)

```bash
export TELEMETRY_ENDPOINT=https://europe-central2-wrack-control.cloudfunctions.net/unifiedIngress
export RPI_DEVICE_ID=rpi-camera-01
export TELEMETRY_DEVICE_TOKEN=<token>   # from cloud/functions/setup-device-tokens.sh
```

Omit these (or pass `--no-send` to `soak_test.py`) to run the pipeline fully locally first —
useful before touching real cloud infrastructure.

## 10. Run

Phase 1 (detection only):

```bash
python3 validation/soak_test.py --detector-model models/yolov8n_640.onnx --decoder yolov8 \
    --video-source 0 --device-id rpi-camera-01 \
    --model-version yolov8n-1.0.0 --pipeline-version edge-vision-0.1.0
```

Phase 2 (+ identification), once steps 5-8 are done:

```bash
python3 validation/soak_test.py --detector-model models/yolov8n_640.onnx --decoder yolov8 \
    --embedding-model models/mobilenet_v3_small_embed.onnx --prototypes prototypes.json \
    --video-source 0 --device-id rpi-camera-01 \
    --model-version yolov8n-1.0.0+mobilenetv3-1.0.0 --pipeline-version edge-vision-0.1.0
```

See `validation/soak_test.py`'s docstring for what it logs (tasks 4.1-4.3 / 8.1-8.3) and why
tasks 4.2/8.2 (false positive rate / identification accuracy) still need you watching your
actual cats — that part can't be scripted.

## GCP infrastructure (Phase 2 storage — separate from the above)

Not part of the Pi deployment flow above. See `../../cloud/cat-recognizer/README.md` for
provisioning the GCS buckets/service accounts enrollment and model export write to.
