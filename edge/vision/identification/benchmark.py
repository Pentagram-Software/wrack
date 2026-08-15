#!/usr/bin/env python3
"""Pi 5 hardware benchmark for the identification embedding backbone
(PEN-261, task 6.2) — mirrors ``detection/benchmark.py``'s structure for
task 1.2, applied to :class:`EmbeddingBackbone` instead of
:class:`CatDetector`.

**Run this on the Raspberry Pi 5 itself** — this session had no network
path to the Pi, so this script is written but not executed; task 6.2 stays
unchecked in tasks.md until you run it. Per `design.md`'s "Compute headroom
is estimated, not measured under load" risk, run this *and*
``detection/benchmark.py`` concurrently (e.g. two terminals) to get a
number close to the real Phase 2 pipeline's combined cost, not just each
model in isolation.

Usage::

    python3 benchmark.py --model mobilenet_v3_small_embed.onnx --iterations 200
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

from identification.embeddings import EmbeddingBackbone  # noqa: E402


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


def _synthetic_crop(size: int = 224) -> np.ndarray:
    """A random crop, used when --crop-dir isn't provided. Measures
    embedding inference cost, not identification accuracy (accuracy is
    task 6.8's job, on real held-out photos)."""
    rng = np.random.default_rng(seed=0)
    return rng.integers(0, 255, size=(size, size, 3), dtype=np.uint8)


def run_benchmark(model_path: str, iterations: int, input_size: tuple) -> dict:
    backbone = EmbeddingBackbone(model_path, input_size=input_size)
    crop = _synthetic_crop()

    latencies_ms = []
    cpu_samples = []
    temp_samples = []

    backbone.embed(crop)  # warm-up

    for _ in range(iterations):
        cpu = _read_cpu_percent()
        if cpu is not None:
            cpu_samples.append(cpu)
        temp = _read_cpu_temp_c()
        if temp is not None:
            temp_samples.append(temp)

        start = time.perf_counter()
        backbone.embed(crop)
        latencies_ms.append((time.perf_counter() - start) * 1000)

    mem = _read_memory_percent()

    return {
        "model_path": model_path,
        "input_size": list(input_size),
        "iterations": iterations,
        "latency_ms": {
            "mean": statistics.mean(latencies_ms),
            "p50": statistics.median(latencies_ms),
            "p95": sorted(latencies_ms)[int(len(latencies_ms) * 0.95)],
            "max": max(latencies_ms),
        },
        "throughput_estimate_per_sec": 1000.0 / statistics.mean(latencies_ms),
        "cpu_percent_mean": statistics.mean(cpu_samples) if cpu_samples else None,
        "memory_percent_last": mem,
        "cpu_temp_c_mean": statistics.mean(temp_samples) if temp_samples else None,
        "cpu_temp_c_max": max(temp_samples) if temp_samples else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Path to the exported embedding backbone ONNX model")
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--input-size", type=int, default=224)
    parser.add_argument("--output", help="Write the JSON report here instead of stdout")
    args = parser.parse_args()

    report = run_benchmark(args.model, args.iterations, (args.input_size, args.input_size))

    output_json = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output_json)
        print("Wrote report to {}".format(args.output))
    else:
        print(output_json)


if __name__ == "__main__":
    main()
