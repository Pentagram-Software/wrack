#!/usr/bin/env python3
"""Export the identification embedding backbone to ONNX (PEN-193, supports
task 6.1/6.2).

**Run this on a dev machine (laptop), NOT the Pi** — same reasoning as
``../detection/export_model.py``. Needs `torch` + `torchvision`, not part of
`edge/vision/requirements.txt` (the Pi *runtime* dependency set)::

    pip install -r requirements-export.txt

Usage::

    python3 export_model.py --output exported_models/mobilenet_v3_small_embed.onnx

Then copy the resulting `.onnx` file to the Pi and benchmark it with
`benchmark.py` (task 6.2), or feed it straight to `enroll.py` (task 6.3/6.4).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def export(output_path: Path, input_size: int) -> None:
    try:
        import torch
        import torch.nn as nn
        import torchvision
    except ImportError:
        print("torch/torchvision not installed — run: pip install -r requirements-export.txt", file=sys.stderr)
        sys.exit(1)

    print("Loading ImageNet-pretrained MobileNetV3-Small...")
    full_model = torchvision.models.mobilenet_v3_small(
        weights=torchvision.models.MobileNet_V3_Small_Weights.IMAGENET1K_V1
    )
    # Keep everything through the global average pool (`avgpool`), drop the
    # classifier head entirely — embeddings.py treats the ONNX graph's raw
    # output as the embedding vector itself, so the graph must stop here,
    # not continue into MobileNetV3's 1000-way ImageNet classifier.
    embedding_model = nn.Sequential(
        full_model.features,
        full_model.avgpool,
        nn.Flatten(),
    )
    embedding_model.eval()

    dummy_input = torch.randn(1, 3, input_size, input_size)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Exporting to ONNX ({}x{} input)...".format(input_size, input_size))
    torch.onnx.export(
        embedding_model,
        dummy_input,
        str(output_path),
        input_names=["input"],
        output_names=["embedding"],
        opset_version=17,
        # Fixed batch size of 1 — matches embeddings.py's one-crop-at-a-time
        # EmbeddingBackbone.embed() calls; no dynamic_axes needed.
    )
    print("Wrote {}".format(output_path))

    with torch.no_grad():
        embedding_dim = embedding_model(dummy_input).shape[-1]
    print("Embedding dimensionality: {}".format(embedding_dim))
    print("Use with: EmbeddingBackbone(\"{}\", input_size=({}, {}))".format(
        output_path, input_size, input_size
    ))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("exported_models/mobilenet_v3_small_embed.onnx"))
    parser.add_argument("--input-size", type=int, default=224)
    args = parser.parse_args()
    export(args.output, args.input_size)


if __name__ == "__main__":
    main()
