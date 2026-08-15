#!/usr/bin/env python3
"""Export a candidate detector to ONNX (PEN-193, supports task 1.1/1.2).

**Run this on a dev machine (laptop), NOT the Pi.** Exporting needs
`ultralytics` (+ its `torch` dependency) — heavy ML tooling that has no
business running on deployed Pi hardware, per `design.md`'s "Training
happens locally, not in the cloud, for V1" decision. Not part of
`edge/vision/requirements.txt` (the Pi *runtime* dependency set) — install
separately::

    pip install -r requirements-export.txt

Usage::

    python3 export_model.py --candidate yolov8n --imgsz 640 --output-dir exported_models/
    python3 export_model.py --candidate yolov5n --imgsz 640 --output-dir exported_models/

Then copy the resulting `.onnx` file to the Pi and benchmark it with
`benchmark.py` (task 1.2) — pass `--decoder` matching the printed value.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

#: Maps each MODEL_SELECTION.md candidate to its Ultralytics weights name and
#: the decode_fn (detector.py) that matches its ONNX export's output shape.
#:
#: Candidate B intentionally decodes with "yolov8", not "yolov5": the
#: `ultralytics` package's `yolov5n.pt` is YOLOv5u (an anchor-free,
#: v8-head variant), not the classic YOLOv5 `[1, N, 85]` head with a
#: separate objectness score. Its ONNX export is the same `[1, 84, N]`
#: shape as YOLOv8n, so decode_yolov8_output is the correct decoder —
#: pairing it with decode_yolov5_output mis-parses every row (wrong
#: objectness/class layout). Confirmed against this project's own
#: benchmark run (--decoder yolov8 against yolov5n_*.onnx worked; see
#: MODEL_SELECTION.md).
CANDIDATES = {
    "yolov8n": {"weights": "yolov8n.pt", "decoder": "yolov8"},
    "yolov5n": {"weights": "yolov5n.pt", "decoder": "yolov8"},
}


def _verify_output_shape(onnx_path: Path, candidate: str) -> None:
    """Best-effort sanity check that the exported model's output shape
    matches what detector.py's decode_yolov{8,5}_output expects — catches a
    mismatched export config early rather than failing confusingly inside
    NMS later. Skipped silently if onnxruntime isn't installed."""
    try:
        import onnxruntime as ort
    except ImportError:
        print("  (onnxruntime not installed — skipping output-shape verification)")
        return

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    output_shape = session.get_outputs()[0].shape
    print("  Output shape: {}".format(output_shape))

    # YOLOv8: [1, 84, N] (4 box coords + 80 class scores, no objectness).
    # YOLOv5: [1, N, 85] (4 box coords + 1 objectness + 80 class scores).
    channel_dim = output_shape[1] if CANDIDATES[candidate]["decoder"] == "yolov8" else output_shape[2]
    expected = 84 if CANDIDATES[candidate]["decoder"] == "yolov8" else 85
    if isinstance(channel_dim, int) and channel_dim != expected:
        print(
            "  WARNING: expected channel dim {} for decode_{}_output, got {} — "
            "the export config (e.g. --nms, different opset) may not match detector.py's "
            "decode assumptions".format(expected, CANDIDATES[candidate]["decoder"], channel_dim)
        )


def export(candidate: str, imgsz: int, output_dir: Path) -> Path:
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics not installed — run: pip install -r requirements-export.txt", file=sys.stderr)
        sys.exit(1)

    weights = CANDIDATES[candidate]["weights"]
    print("Loading {} (downloads pretrained COCO weights on first run)...".format(weights))
    model = YOLO(weights)

    print("Exporting to ONNX at {}x{}...".format(imgsz, imgsz))
    exported_path = Path(model.export(format="onnx", imgsz=imgsz))

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "{}_{}.onnx".format(candidate, imgsz)
    shutil.copy(exported_path, destination)
    print("Wrote {}".format(destination))

    _verify_output_shape(destination, candidate)

    print(
        "Use with: CatDetector(\"{}\", decode_fn=decode_{}_output, input_size=({}, {}))".format(
            destination, CANDIDATES[candidate]["decoder"], imgsz, imgsz
        )
    )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=CANDIDATES.keys(), required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--output-dir", type=Path, default=Path("exported_models"))
    args = parser.parse_args()
    export(args.candidate, args.imgsz, args.output_dir)


if __name__ == "__main__":
    main()
