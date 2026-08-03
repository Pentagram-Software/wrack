"""Unit tests for detection/detector.py (PEN-193, tasks 1.4-1.5).

No real ONNX model or onnxruntime install is needed: decode functions are
tested against synthetic model-output arrays, and CatDetector is tested with
a fake injected session.
"""

import numpy as np
import pytest

from detection.coco import COCO_CAT_CLASS_ID
from detection.detector import (
    CatDetector,
    DetectionResult,
    decode_yolov5_output,
    decode_yolov8_output,
)


def _yolov8_row(class_id, confidence, cx=0.5, cy=0.5, w=0.2, h=0.2, num_classes=80):
    """Build one [84] row: [cx, cy, w, h, *class_scores]."""
    row = np.zeros(4 + num_classes, dtype=np.float32)
    row[:4] = [cx, cy, w, h]
    row[4 + class_id] = confidence
    return row


def _yolov5_row(class_id, confidence, objectness=1.0, cx=0.5, cy=0.5, w=0.2, h=0.2, num_classes=80):
    """Build one [85] row: [cx, cy, w, h, objectness, *class_scores]. Class
    score is confidence/objectness so objectness * class_score == confidence."""
    row = np.zeros(5 + num_classes, dtype=np.float32)
    row[:4] = [cx, cy, w, h]
    row[4] = objectness
    row[5 + class_id] = confidence / objectness if objectness else 0.0
    return row


class TestDecodeYolov8Output:
    def test_extracts_cat_detection_above_threshold(self):
        rows = np.stack([_yolov8_row(COCO_CAT_CLASS_ID, 0.9)])
        outputs = [rows.transpose(1, 0)[np.newaxis, ...]]  # [1, 84, N]
        detections = decode_yolov8_output(outputs, confidence_threshold=0.5)
        assert len(detections) == 1
        assert detections[0].class_id == COCO_CAT_CLASS_ID
        assert detections[0].confidence == pytest.approx(0.9)

    def test_below_threshold_dropped(self):
        rows = np.stack([_yolov8_row(COCO_CAT_CLASS_ID, 0.2)])
        outputs = [rows.transpose(1, 0)[np.newaxis, ...]]
        detections = decode_yolov8_output(outputs, confidence_threshold=0.5)
        assert detections == []

    def test_bbox_derived_from_center_wh(self):
        rows = np.stack([_yolov8_row(COCO_CAT_CLASS_ID, 0.9, cx=0.5, cy=0.5, w=0.2, h=0.4)])
        outputs = [rows.transpose(1, 0)[np.newaxis, ...]]
        detections = decode_yolov8_output(outputs, confidence_threshold=0.5)
        x_min, y_min, x_max, y_max = detections[0].bbox
        assert x_min == pytest.approx(0.4)
        assert x_max == pytest.approx(0.6)
        assert y_min == pytest.approx(0.3)
        assert y_max == pytest.approx(0.7)

    def test_overlapping_detections_suppressed_by_nms(self):
        rows = np.stack(
            [
                _yolov8_row(COCO_CAT_CLASS_ID, 0.9, cx=0.5, cy=0.5),
                _yolov8_row(COCO_CAT_CLASS_ID, 0.7, cx=0.51, cy=0.5),  # near-duplicate box
            ]
        )
        outputs = [rows.transpose(1, 0)[np.newaxis, ...]]
        detections = decode_yolov8_output(outputs, confidence_threshold=0.5, iou_threshold=0.45)
        assert len(detections) == 1
        assert detections[0].confidence == pytest.approx(0.9)


class TestDecodeYolov5Output:
    def test_confidence_is_objectness_times_class_score(self):
        rows = np.stack([_yolov5_row(COCO_CAT_CLASS_ID, confidence=0.8, objectness=0.8)])
        outputs = [rows[np.newaxis, ...]]  # [1, N, 85]
        detections = decode_yolov5_output(outputs, confidence_threshold=0.5)
        assert len(detections) == 1
        assert detections[0].confidence == pytest.approx(0.8)

    def test_below_threshold_dropped(self):
        rows = np.stack([_yolov5_row(COCO_CAT_CLASS_ID, confidence=0.1, objectness=1.0)])
        outputs = [rows[np.newaxis, ...]]
        assert decode_yolov5_output(outputs, confidence_threshold=0.5) == []

    def test_non_cat_class_included_before_filtering(self):
        rows = np.stack([_yolov5_row(class_id=0, confidence=0.9, objectness=0.9)])
        outputs = [rows[np.newaxis, ...]]
        detections = decode_yolov5_output(outputs, confidence_threshold=0.5)
        assert len(detections) == 1
        assert detections[0].class_id == 0


class _FakeInput:
    name = "images"


class _FakeSession:
    """Fake onnxruntime.InferenceSession — records the last feed dict and
    returns pre-canned outputs from .run()."""

    def __init__(self, outputs):
        self._outputs = outputs
        self.last_feed = None

    def get_inputs(self):
        return [_FakeInput()]

    def run(self, output_names, feed_dict):
        self.last_feed = feed_dict
        return self._outputs


class TestCatDetector:
    def _make_detector(self, outputs, **kwargs):
        session = _FakeSession(outputs)
        return CatDetector(
            "unused-model-path.onnx",
            session_factory=lambda path: session,
            **kwargs,
        ), session

    def test_present_when_cat_detected_above_threshold(self):
        rows = np.stack([_yolov8_row(COCO_CAT_CLASS_ID, 0.9)])
        outputs = [rows.transpose(1, 0)[np.newaxis, ...]]
        detector, _ = self._make_detector(outputs)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = detector.infer(frame)

        assert isinstance(result, DetectionResult)
        assert result.present is True
        assert result.confidence == pytest.approx(0.9)
        assert result.crop_bbox is not None

    def test_absent_when_no_cat_detected(self):
        rows = np.stack([_yolov8_row(class_id=0, confidence=0.95)])  # not a cat
        outputs = [rows.transpose(1, 0)[np.newaxis, ...]]
        detector, _ = self._make_detector(outputs)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = detector.infer(frame)

        assert result.present is False
        assert result.confidence == 0.0
        assert result.crop_bbox is None

    def test_absent_when_below_confidence_threshold(self):
        rows = np.stack([_yolov8_row(COCO_CAT_CLASS_ID, 0.1)])
        outputs = [rows.transpose(1, 0)[np.newaxis, ...]]
        detector, _ = self._make_detector(outputs, confidence_threshold=0.5)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = detector.infer(frame)

        assert result.present is False

    def test_highest_confidence_cat_wins_when_multiple_present(self):
        rows = np.stack(
            [
                _yolov8_row(COCO_CAT_CLASS_ID, 0.6, cx=0.2, cy=0.2),
                _yolov8_row(COCO_CAT_CLASS_ID, 0.95, cx=0.8, cy=0.8),
            ]
        )
        outputs = [rows.transpose(1, 0)[np.newaxis, ...]]
        detector, _ = self._make_detector(outputs)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = detector.infer(frame)

        assert result.confidence == pytest.approx(0.95)

    def test_preprocess_resizes_to_input_size_and_feeds_input_name(self):
        rows = np.stack([_yolov8_row(COCO_CAT_CLASS_ID, 0.9)])
        outputs = [rows.transpose(1, 0)[np.newaxis, ...]]
        detector, session = self._make_detector(outputs, input_size=(320, 320))
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        detector.infer(frame)

        assert "images" in session.last_feed
        fed = session.last_feed["images"]
        assert fed.shape == (1, 3, 320, 320)
        assert fed.dtype == np.float32

    def test_yolov5_decode_fn_can_be_injected(self):
        rows = np.stack([_yolov5_row(COCO_CAT_CLASS_ID, confidence=0.85, objectness=0.85)])
        outputs = [rows[np.newaxis, ...]]
        detector, _ = self._make_detector(outputs, decode_fn=decode_yolov5_output)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = detector.infer(frame)

        assert result.present is True
        assert result.confidence == pytest.approx(0.85)
