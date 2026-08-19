#!/usr/bin/env python3
"""Pi 5 soak test harness (PEN-252–254/PEN-270–272, tasks 4.1-4.3 and 8.1-8.3).

Runs the full :class:`pipeline.VisionPipeline` against a live camera or a
recorded video file for an extended period, logging FPS/CPU/memory/thermal
at a fixed interval and every confirmed cat event. **Not run this session**
(no Pi access) — this covers the *mechanical* part of tasks 4.1/4.3 and
8.1/8.3 (run it, watch resource usage stay in bounds, confirm no manual
restart is needed); tasks 4.2 and 8.2 (false positive rate / identification
accuracy against PRD §9 targets) additionally require **watching your actual
cats** during the run and comparing confirmed events to what really
happened — that part can't be scripted.

Usage — Phase 1 (detection only, task group 4)::

    python3 soak_test.py --detector-model yolov8n.onnx --decoder yolov8 \\
        --video-source 0 --device-id rpi-camera-01 \\
        --model-version yolov8n-1.0.0 --pipeline-version edge-vision-0.1.0

Usage — Phase 2 (detection + identification, task group 8), once
enrollment (6.3/6.4) has produced ``prototypes.json``::

    python3 soak_test.py --detector-model yolov8n.onnx --decoder yolov8 \\
        --embedding-model mobilenet_v3_small_embed.onnx --prototypes prototypes.json \\
        --identity-threshold 0.65 \\
        --video-source 0 --device-id rpi-camera-01 \\
        --model-version yolov8n-1.0.0+mobilenetv3-1.0.0 --pipeline-version edge-vision-0.1.0

``--video-source`` accepts a camera index (e.g. ``0``) or a path to a
recorded video file — this deliberately reads via OpenCV's own
``VideoCapture`` rather than depending on ``edge/video-streamer/``'s
capture path, since that shared-capture-path tap-in (task 1.4's other half)
isn't wired up yet — see ``pipeline.py``'s module docstring. Swap
``_video_frame_source`` for the real shared path once that integration
exists, without changing anything else here.

Set ``--send/--no-send`` to control whether confirmed events actually POST
to the telemetry endpoint (``RpiTelemetrySender``) or just log locally —
useful for a first dry run before touching real cloud infrastructure.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from detection.detector import CatDetector, decode_yolov5_output, decode_yolov8_output  # noqa: E402
from identification.embeddings import EmbeddingBackbone  # noqa: E402
from identification.enroll import load_prototypes  # noqa: E402
from identification.identifier import CatIdentifier  # noqa: E402
from pipeline import VisionPipeline  # noqa: E402

DECODERS = {"yolov8": decode_yolov8_output, "yolov5": decode_yolov5_output}


def _video_frame_source(video_source):
    import cv2

    capture = cv2.VideoCapture(video_source)
    if not capture.isOpened():
        raise RuntimeError("could not open video source: {!r}".format(video_source))

    def _source():
        ok, frame = capture.read()
        return frame if ok else None

    return _source


def _read_cpu_temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def _read_cpu_percent():
    try:
        import psutil

        return psutil.cpu_percent(interval=None)
    except ImportError:
        return None


def _read_memory_percent():
    try:
        import psutil

        return psutil.virtual_memory().percent
    except ImportError:
        return None


def _log_resources(log_path: Optional[Path]) -> None:
    record = {
        "ts": time.time(),
        "cpu_percent": _read_cpu_percent(),
        "memory_percent": _read_memory_percent(),
        "cpu_temp_c": _read_cpu_temp_c(),
    }
    line = json.dumps(record)
    print("[resources] {}".format(line))
    if log_path:
        with open(log_path, "a") as f:
            f.write(line + "\n")


def _log_event(event: dict, log_path: Optional[Path]) -> None:
    print("[event] {}".format(json.dumps(event)))
    if log_path:
        with open(log_path, "a") as f:
            f.write(json.dumps(event) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detector-model", required=True)
    parser.add_argument("--decoder", choices=DECODERS.keys(), default="yolov8")
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=None,
        help="Detection confidence threshold; falls back to CAT_DETECTION_CONFIDENCE_THRESHOLD env var, then 0.5",
    )
    parser.add_argument("--embedding-model", help="Phase 2 only — enables identification")
    parser.add_argument("--prototypes", help="Phase 2 only — prototypes.json from enroll.py")
    parser.add_argument(
        "--identity-threshold",
        type=float,
        default=None,
        help=(
            "Phase 2 only — identity confidence threshold; falls back to "
            "CAT_IDENTITY_CONFIDENCE_THRESHOLD env var, then 0.6 "
            "(see evaluate_threshold.py for picking a value)"
        ),
    )
    parser.add_argument("--video-source", required=True, help="Camera index (e.g. 0) or video file path")
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--pipeline-version", required=True)
    parser.add_argument("--fps", type=float, default=3.0)
    parser.add_argument("--resource-log-interval-seconds", type=float, default=30.0)
    parser.add_argument("--log-file", help="Append JSONL resource/event records here too")
    parser.add_argument("--send", dest="send", action="store_true", default=True)
    parser.add_argument("--no-send", dest="send", action="store_false")
    parser.add_argument(
        "--endpoint",
        help="Telemetry endpoint URL (falls back to TELEMETRY_ENDPOINT env var) — only used with --send",
    )
    args = parser.parse_args()

    if bool(args.embedding_model) != bool(args.prototypes):
        parser.error("--embedding-model and --prototypes must be given together (Phase 2) or not at all")

    detector = CatDetector(
        args.detector_model,
        decode_fn=DECODERS[args.decoder],
        confidence_threshold=args.confidence_threshold,
    )

    embedding_backbone = None
    identifier = None
    if args.embedding_model:
        embedding_backbone = EmbeddingBackbone(args.embedding_model)
        identifier = CatIdentifier(load_prototypes(args.prototypes), confidence_threshold=args.identity_threshold)

    send_event = None
    if args.send:
        from telemetry.sender import RpiTelemetrySender

        sender = RpiTelemetrySender(endpoint=args.endpoint, device_id=args.device_id)
        send_event = lambda event: sender.send_events([event])  # noqa: E731

    log_path = Path(args.log_file) if args.log_file else None

    def _on_event(event):
        _log_event(event, log_path)
        if send_event:
            send_event(event)

    pipeline = VisionPipeline(
        detector,
        _video_frame_source(args.video_source),
        embedding_backbone=embedding_backbone,
        identifier=identifier,
        device_id=args.device_id,
        model_version=args.model_version,
        pipeline_version=args.pipeline_version,
        send_event=_on_event,
    )

    print("Starting soak test — Ctrl+C to stop. Resource usage logged every {}s.".format(
        args.resource_log_interval_seconds
    ))
    last_resource_log = 0.0
    interval = 1.0 / args.fps
    try:
        while True:
            pipeline.run_once()
            now = time.time()
            if now - last_resource_log >= args.resource_log_interval_seconds:
                _log_resources(log_path)
                last_resource_log = now
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
