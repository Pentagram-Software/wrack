# Detector candidate selection (task 1.1)

Two pretrained, COCO-class, ONNX-exportable detectors to benchmark on the Pi 5 (task 1.2),
per `design.md`'s open question "exact detector architecture (deferred until the Pi hardware
benchmark produces real FPS/CPU/thermal numbers for candidate ONNX models)".

## Candidate A — YOLOv8n

- Ultralytics `yolov8n.pt`, COCO-pretrained, ~3.2M params.
- Export: `yolo export model=yolov8n.pt format=onnx imgsz=640` (or `imgsz=320` for a
  lower-latency variant worth benchmarking alongside the default).
- ONNX Runtime CPU support is mature; widely benchmarked on Pi 5 already (community numbers
  land in the 15-30ms/inference range at 640x640 on Pi 5 CPU, faster at 320x320).
- Output format: single tensor, shape `[1, 84, N]` (4 box coords + 80 COCO class scores,
  N = anchor points) — no separate objectness score, decode is argmax-over-classes per anchor
  then NMS. `detector.py`'s default decoder targets this format.

## Candidate B — YOLOv5n

- Ultralytics `yolov5n.pt`, COCO-pretrained, ~1.9M params — smaller and faster than YOLOv8n,
  at some accuracy cost.
- Export: `yolo export model=yolov5n.pt format=onnx imgsz=640` (same Ultralytics CLI, same
  ONNX Runtime CPU execution path).
- **Output format: `[1, 84, N]`, decoded with `decode_yolov8_output` — not the classic YOLOv5
  `[1, N, 85]` head.** The `ultralytics` package's `yolov5n.pt` weights are YOLOv5u: an
  anchor-free, v8-style head with no separate objectness score, confirmed against a real
  export from this project's `export_model.py` and its benchmark run (`--decoder yolov8`
  against `yolov5n_*.onnx` produced sane detections; `--decoder yolov5` mis-parses every row).
  `export_model.py`'s `CANDIDATES` maps `yolov5n` to `decoder: "yolov8"` accordingly.
  `decode_yolov5_output` (the classic `[1, N, 85]` head) remains available in `detector.py`
  for a genuine classic-YOLOv5 export (e.g. from the standalone `ultralytics/yolov5` repo),
  which this candidate does not use.

## Why these two

- Both are COCO-pretrained (class id 15 = `cat`, filtered by `coco.filter_to_cat`) — no
  training needed for V1, matching design.md's "training happens locally, not in the cloud"
  decision (in this case, no training at all).
- Both export to ONNX via the same well-supported Ultralytics tooling, keeping the export step
  identical regardless of which candidate wins the benchmark.
- Meaningfully different size/accuracy trade-off (YOLOv8n more accurate, YOLOv5n smaller/faster)
  makes the Pi 5 benchmark (task 1.2) an actual choice rather than a formality.

## What's NOT decided here

- Final pick (task 1.3) — depends on real FPS/CPU/thermal numbers from `benchmark.py` running
  on the Pi 5, which requires physical hardware access this session didn't have.
- Input resolution — benchmark both 640x640 and a smaller size (e.g. 320x320) per candidate if
  time allows; smaller input trades accuracy for latency/thermal headroom.
