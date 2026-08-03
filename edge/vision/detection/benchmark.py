#!/usr/bin/env python3
"""Pi 5 hardware benchmark for candidate cat detectors (PEN-193, task 1.2).

**Run this on the Raspberry Pi 5 itself** — this session had no network path
to the Pi (`raspberrypi.local` doesn't resolve from the dev machine), so this
script is written but not executed; task 1.2/1.3 stay unchecked in tasks.md
until you run it and report back the numbers (task 1.3 picks the detector
based on this output).

Usage::

    # Run standalone (detector only):
    python3 benchmark.py --model yolov8n.onnx --decoder yolov8 --iterations 200

    # Run with edge/video-streamer also active, per edge/vision/README.md's
    # Phase 1 milestone ("1-2 ONNX detectors on Pi 5 -> FPS/CPU/thermal
    # table") — start the streamer separately first, then run this with
    # --concurrent-streamer to note in the report that it was running:
    python3 benchmark.py --model yolov8n.onnx --decoder yolov8 --concurrent-streamer

Reads CPU%/memory the same way ``edge/monitoring/system_metrics_collector.py``
already does on this fleet (via ``psutil`` when available), and thermal the
same way ``telemetry/schemas.py``'s ``system_metrics`` payload treats
``cpu_temp_c`` — optional, isolated failure, never crashes the run.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from detection.detector import CatDetector, decode_yolov5_output, decode_yolov8_output  # noqa: E402

DECODERS = {
    "yolov8": decode_yolov8_output,
    "yolov5": decode_yolov5_output,
}


def _read_cpu_temp_c() -> "float | None":
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def _read_cpu_percent() -> "float | None":
    try:
        import psutil

        return psutil.cpu_percent(interval=None)
    except ImportError:
        return None


def _read_memory_percent() -> "float | None":
    try:
        import psutil

        return psutil.virtual_memory().percent
    except ImportError:
        return None


def _synthetic_frame(width: int = 640, height: int = 480) -> np.ndarray:
    """A random frame, used when --frame-dir isn't provided. Good enough for
    latency/FPS/CPU/thermal (this script measures inference cost, not
    detection accuracy — accuracy is task 8.2's job, on real footage)."""
    rng = np.random.default_rng(seed=0)
    return rng.integers(0, 255, size=(height, width, 3), dtype=np.uint8)


def run_benchmark(
    model_path: str,
    decoder_name: str,
    iterations: int,
    input_size: tuple,
    confidence_threshold: float,
) -> dict:
    detector = CatDetector(
        model_path,
        decode_fn=DECODERS[decoder_name],
        input_size=input_size,
        confidence_threshold=confidence_threshold,
    )
    frame = _synthetic_frame()

    latencies_ms = []
    cpu_samples = []
    temp_samples = []

    # Warm-up (first ONNX Runtime call includes graph optimization overhead
    # that wouldn't reflect steady-state Pi-side latency).
    detector.infer(frame)

    for _ in range(iterations):
        cpu = _read_cpu_percent()
        if cpu is not None:
            cpu_samples.append(cpu)
        temp = _read_cpu_temp_c()
        if temp is not None:
            temp_samples.append(temp)

        start = time.perf_counter()
        detector.infer(frame)
        latencies_ms.append((time.perf_counter() - start) * 1000)

    mem = _read_memory_percent()

    return {
        "model_path": model_path,
        "decoder": decoder_name,
        "input_size": list(input_size),
        "iterations": iterations,
        "latency_ms": {
            "mean": statistics.mean(latencies_ms),
            "p50": statistics.median(latencies_ms),
            "p95": sorted(latencies_ms)[int(len(latencies_ms) * 0.95)],
            "max": max(latencies_ms),
        },
        "fps_estimate": 1000.0 / statistics.mean(latencies_ms),
        "cpu_percent_mean": statistics.mean(cpu_samples) if cpu_samples else None,
        "memory_percent_last": mem,
        "cpu_temp_c_mean": statistics.mean(temp_samples) if temp_samples else None,
        "cpu_temp_c_max": max(temp_samples) if temp_samples else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Path to the exported ONNX model")
    parser.add_argument("--decoder", choices=DECODERS.keys(), required=True)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=640)
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    parser.add_argument(
        "--concurrent-streamer",
        action="store_true",
        help="Note in the report that edge/video-streamer was running concurrently "
        "(start it yourself before running this script — this flag only annotates output)",
    )
    parser.add_argument("--output", help="Write the JSON report here instead of stdout")
    args = parser.parse_args()

    report = run_benchmark(
        args.model,
        args.decoder,
        args.iterations,
        (args.width, args.height),
        args.confidence_threshold,
    )
    report["concurrent_streamer"] = args.concurrent_streamer

    output_json = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output_json)
        print("Wrote report to {}".format(args.output))
    else:
        print(output_json)


if __name__ == "__main__":
    main()
