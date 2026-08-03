# Embedding backbone selection (task 6.1)

Per `design.md`'s decision "Identification uses embeddings + per-cat prototypes, not a
closed-set classifier": a frozen, CPU-friendly, ImageNet-pretrained backbone, used purely as a
feature extractor (no cat-specific training, no fine-tuning for V1).

## Choice — MobileNetV3-Small

- ImageNet-pretrained, ~2.5M params, designed for mobile/embedded CPU inference — the same
  class of model `edge/vision/README.md`'s training-architecture section already names
  (alongside EfficientNet-Lite0) as a CPU-friendly option.
- Embedding = the 576-dim penultimate (pre-classifier) layer output, L2-normalized —
  `embeddings.py`'s `EmbeddingBackbone.embed()` reads whatever the ONNX export's output tensor
  is, so the exact dimensionality is a property of the exported model, not hardcoded here.
- Export: standard `torch.onnx.export` from `torchvision.models.mobilenet_v3_small(weights=...)`
  with the final `classifier` head removed (keep only through the global average pool), or
  export the full model and read the penultimate layer's output name.
- ARM64/ONNX Runtime CPU support is mature — same execution provider (`CPUExecutionProvider`)
  as the detector backbones in `../detection/MODEL_SELECTION.md`.

## Why this over alternatives

- **Over EfficientNet-Lite0**: comparable CPU-friendliness; MobileNetV3-Small has a smaller
  embedding dimension (576 vs ~1280) and slightly lower FLOPs, worth preferring as the first
  candidate to benchmark (task 6.2) given the Pi 5 will also be running the detector
  concurrently — the smaller model has more of a safety margin if compute headroom turns out
  tighter than the streamer-only measurements in `design.md`'s Context section suggest.
- **Over a face/animal-specific re-identification model**: no public model targets
  *individual* pet identification for arbitrary breeds — this is why `design.md` chose the
  generic-backbone-plus-prototype approach in the first place rather than looking for an
  off-the-shelf "cat recognition" model that doesn't exist for this use case.
- **Over training a custom embedding model**: `design.md`'s "Training happens locally, not in
  the cloud, for V1" decision explicitly rules out any training loop for identification —
  a frozen pretrained backbone needs none.

## What's NOT decided here

- Benchmark numbers (task 6.2) — needs Pi 5 hardware access this session didn't have.
- Precise export configuration (opset version, whether to keep the pooling layer as a separate
  ONNX output vs. relying on the classifier's penultimate activation) — a task 6.1
  implementation detail to finalize once export is actually run, not an architectural
  commitment `design.md` needs to lock in (per its own "Non-Goals").
