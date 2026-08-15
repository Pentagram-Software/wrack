"""ONNX cat detector wrapper (PEN-241/PEN-242, tasks 1.4-1.5).

Wraps an ONNX Runtime session for one of the candidates in
``MODEL_SELECTION.md``, decoding raw model output into ``Detection`` objects
(``coco.py``), filtering to the cat class, and reducing to this frame's
single highest-confidence result — implementing the cat-detection spec's
"Per-Frame Detection Confidence" requirement (presence/absence, a confidence
score, and a crop when present).

The decode step (``decode_fn``) is pluggable because task 1.3 (pick the
detector) is still open — ``MODEL_SELECTION.md``'s two candidates use
different output tensor shapes (YOLOv8n's anchor-free `[1, 84, N]` vs
YOLOv5n's `[1, N, 85]` head), and swapping the eventual pick shouldn't
require changing this wrapper's public interface. ``onnxruntime`` is only
imported inside the default session factory (not at module import time) so
this module — and its decode/filter logic — stays testable on a machine
without the Pi's inference runtime installed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from .coco import Detection, filter_to_cat

#: Default minimum per-class confidence to keep a raw detection, used when
#: neither an explicit constructor arg nor the CAT_DETECTION_CONFIDENCE_THRESHOLD
#: env var is set.
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


@dataclass(frozen=True)
class DetectionResult:
    """Per-frame detection outcome (cat-detection spec: "Per-Frame Detection
    Confidence"). ``crop_bbox`` is ``None`` exactly when ``present`` is
    ``False``."""

    present: bool
    confidence: float
    crop_bbox: Optional[Tuple[float, float, float, float]]


DecodeFn = Callable[[Sequence[np.ndarray], float], List[Detection]]


def _nms(detections: List[Detection], iou_threshold: float) -> List[Detection]:
    """Greedy IoU-based non-max suppression, highest confidence first."""
    ordered = sorted(detections, key=lambda d: d.confidence, reverse=True)
    kept: List[Detection] = []
    for candidate in ordered:
        if all(_iou(candidate.bbox, k.bbox) <= iou_threshold for k in kept):
            kept.append(candidate)
    return kept


def _iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    inter_w, inter_h = max(0.0, inter_x2 - inter_x1), max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area == 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    return inter_area / union if union > 0 else 0.0


def decode_yolov8_output(
    outputs: Sequence[np.ndarray],
    confidence_threshold: float,
    iou_threshold: float = 0.45,
) -> List[Detection]:
    """Decode a YOLOv8-style ONNX export: single tensor `[1, 84, N]`
    (4 box coords in xywh, center-based, + 80 COCO class scores, no
    objectness). Box coords are in **model-input pixel space** (e.g.
    `[0, imgsz]`), matching what a default Ultralytics `format=onnx` export
    actually emits — *not* normalized to [0, 1]. ``CatDetector.infer``
    normalizes against ``input_size`` after this returns."""
    raw = outputs[0]
    if raw.ndim == 3:
        raw = raw[0]
    # raw: [84, N] -> [N, 84]
    raw = raw.transpose(1, 0)
    detections: List[Detection] = []
    for row in raw:
        cx, cy, w, h = row[:4]
        class_scores = row[4:]
        class_id = int(np.argmax(class_scores))
        confidence = float(class_scores[class_id])
        if confidence < confidence_threshold:
            continue
        x_min, y_min = cx - w / 2, cy - h / 2
        x_max, y_max = cx + w / 2, cy + h / 2
        detections.append(
            Detection(
                class_id=class_id,
                confidence=confidence,
                bbox=(float(x_min), float(y_min), float(x_max), float(y_max)),
            )
        )
    return _nms(detections, iou_threshold)


def decode_yolov5_output(
    outputs: Sequence[np.ndarray],
    confidence_threshold: float,
    iou_threshold: float = 0.45,
) -> List[Detection]:
    """Decode a YOLOv5-style ONNX export: single tensor `[1, N, 85]`
    (4 box coords in xywh, center-based, + 1 objectness + 80 COCO class
    scores). Box coords are in **model-input pixel space** (e.g.
    `[0, imgsz]`), matching the classic YOLOv5 head — *not* normalized to
    [0, 1]. ``CatDetector.infer`` normalizes against ``input_size`` after
    this returns. Final confidence is objectness * class score, per the
    standard YOLOv5 head."""
    raw = outputs[0]
    if raw.ndim == 3:
        raw = raw[0]
    detections: List[Detection] = []
    for row in raw:
        cx, cy, w, h = row[:4]
        objectness = row[4]
        class_scores = row[5:]
        class_id = int(np.argmax(class_scores))
        confidence = float(objectness * class_scores[class_id])
        if confidence < confidence_threshold:
            continue
        x_min, y_min = cx - w / 2, cy - h / 2
        x_max, y_max = cx + w / 2, cy + h / 2
        detections.append(
            Detection(
                class_id=class_id,
                confidence=confidence,
                bbox=(float(x_min), float(y_min), float(x_max), float(y_max)),
            )
        )
    return _nms(detections, iou_threshold)


class CatDetector:
    """Runs one ONNX cat detector against frames, producing a
    :class:`DetectionResult` per call to :meth:`infer`.

    Parameters
    ----------
    model_path:
        Path to the exported ONNX model (see ``MODEL_SELECTION.md``).
    decode_fn:
        Decodes raw ONNX Runtime outputs into ``Detection`` objects. Defaults
        to :func:`decode_yolov8_output` (Candidate A); pass
        :func:`decode_yolov5_output` for Candidate B.
    input_size:
        ``(width, height)`` the model expects. Defaults to ``(640, 640)``.
    confidence_threshold:
        Minimum per-class confidence to keep a raw detection before cat
        filtering and NMS. Falls back to the CAT_DETECTION_CONFIDENCE_THRESHOLD
        environment variable, then DEFAULT_CONFIDENCE_THRESHOLD, matching the
        env-var-configurable convention established by
        ``events.lifecycle.LifecycleConfig`` (PRD §8/§12 requires this
        threshold be externally configurable, not hardcoded).
    session_factory:
        Builds the ONNX Runtime session from ``model_path``. Defaults to a
        real ``onnxruntime.InferenceSession`` (imported lazily, so this
        class — and the decode functions above — stay testable without
        ``onnxruntime`` installed). Tests inject a fake session here.
    """

    def __init__(
        self,
        model_path: str,
        *,
        decode_fn: DecodeFn = decode_yolov8_output,
        input_size: Tuple[int, int] = (640, 640),
        confidence_threshold: Optional[float] = None,
        session_factory: Optional[Callable[[str], object]] = None,
    ) -> None:
        session_factory = session_factory or self._default_session_factory
        self._session = session_factory(model_path)
        self._input_name = self._session.get_inputs()[0].name
        self.decode_fn = decode_fn
        self.input_size = input_size
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else float(os.environ.get("CAT_DETECTION_CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD))
        )

    @staticmethod
    def _default_session_factory(model_path: str):
        import onnxruntime as ort  # local import — see class docstring

        return ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    def infer(self, frame: np.ndarray) -> DetectionResult:
        """Run detection on one BGR ``frame`` (H, W, 3, as produced by
        OpenCV's ``VideoCapture``) and return the single highest-confidence
        cat detection, or an absent result."""
        preprocessed = self._preprocess(frame)
        outputs = self._session.run(None, {self._input_name: preprocessed})
        detections = self.decode_fn(outputs, self.confidence_threshold)
        cats = filter_to_cat(detections)
        if not cats:
            return DetectionResult(present=False, confidence=0.0, crop_bbox=None)
        best = max(cats, key=lambda d: d.confidence)
        return DetectionResult(
            present=True,
            confidence=best.confidence,
            crop_bbox=self._normalize_bbox(best.bbox),
        )

    def _normalize_bbox(
        self, bbox: Tuple[float, float, float, float]
    ) -> Tuple[float, float, float, float]:
        """Convert a decoder-output bbox from model-input pixel space
        (``[0, input_size]``) to normalized ``[0, 1]`` fractions of the
        frame, clamping to the valid range. Since ``_preprocess`` resizes
        each axis independently to ``input_size`` (no letterbox padding),
        dividing by ``input_size`` maps a model-pixel coordinate directly
        back onto the original frame's fractional coordinate on that axis,
        with no separate pad/gain bookkeeping needed."""
        width, height = self.input_size
        x_min, y_min, x_max, y_max = bbox
        return (
            min(max(x_min / width, 0.0), 1.0),
            min(max(y_min / height, 0.0), 1.0),
            min(max(x_max / width, 0.0), 1.0),
            min(max(y_max / height, 0.0), 1.0),
        )

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Convert BGR (OpenCV) -> RGB (what COCO-pretrained YOLO expects),
        resize to ``input_size``, scale to [0, 1], convert HWC -> NCHW."""
        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, self.input_size)
        normalized = resized.astype(np.float32) / 255.0
        chw = normalized.transpose(2, 0, 1)
        return np.expand_dims(chw, axis=0)
