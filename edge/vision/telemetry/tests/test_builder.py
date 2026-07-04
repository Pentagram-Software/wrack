"""Unit tests for telemetry/builder.py (vision_detection event builder, PEN-169)."""

import uuid

import pytest

from telemetry.builder import build_vision_detection_event
from telemetry.collector import RpiTelemetryCollector
from telemetry.schemas import ValidationError


def _detection(**overrides):
    detection = {
        "label": "cat",
        "creature_category": "animal",
        "confidence": 0.91,
        "bbox_norm": [0.12, 0.34, 0.45, 0.78],
    }
    detection.update(overrides)
    return detection


class TestBuildVisionDetectionEvent:
    def test_empty_detections_returns_valid_envelope(self):
        event = build_vision_detection_event(frame_index=0, model_id="m", detections=[])
        assert event["event_type"] == "vision_detection"
        assert event["source"] == "rpi"
        assert event["payload"]["detection_count"] == 0
        assert event["payload"]["detections"] == []

    def test_event_id_is_valid_uuid(self):
        event = build_vision_detection_event(frame_index=0, model_id="m", detections=[])
        uuid.UUID(event["event_id"])

    def test_detection_count_matches_len(self):
        event = build_vision_detection_event(
            frame_index=1, model_id="m", detections=[_detection(), _detection(label="dog")]
        )
        assert event["payload"]["detection_count"] == 2
        assert len(event["payload"]["detections"]) == 2

    def test_optional_fields_included_when_provided(self):
        event = build_vision_detection_event(
            frame_index=4821,
            model_id="yolov8n-wrack",
            detections=[_detection()],
            inference_latency_ms=87.4,
            model_version="1.2.0",
            analysis_fps=4.9,
            scene_summary="cat, center",
        )
        payload = event["payload"]
        assert payload["inference_latency_ms"] == 87.4
        assert payload["model_version"] == "1.2.0"
        assert payload["analysis_fps"] == 4.9
        assert payload["scene_summary"] == "cat, center"

    def test_optional_fields_omitted_when_not_provided(self):
        event = build_vision_detection_event(frame_index=0, model_id="m", detections=[])
        payload = event["payload"]
        assert "inference_latency_ms" not in payload
        assert "model_version" not in payload
        assert "analysis_fps" not in payload
        assert "scene_summary" not in payload

    def test_device_id_and_session_id_forwarded(self):
        event = build_vision_detection_event(
            frame_index=0,
            model_id="m",
            detections=[],
            device_id="rpi-camera-01",
            session_id="sess-1",
        )
        assert event["device_id"] == "rpi-camera-01"
        assert event["session_id"] == "sess-1"

    def test_device_id_and_session_id_default_to_none(self):
        event = build_vision_detection_event(frame_index=0, model_id="m", detections=[])
        assert event["device_id"] is None
        assert event["session_id"] is None

    def test_detection_count_mismatch_cannot_occur_via_builder(self):
        """The builder always derives detection_count from len(detections),
        so this failure mode can only be exercised via schemas.validate_event
        directly on a hand-built payload (see test_schemas.py)."""
        event = build_vision_detection_event(
            frame_index=0, model_id="m", detections=[_detection(), _detection()]
        )
        assert event["payload"]["detection_count"] == len(event["payload"]["detections"])

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            build_vision_detection_event(
                frame_index=0, model_id="m", detections=[_detection(confidence=1.5)]
            )

    def test_malformed_bbox_raises(self):
        with pytest.raises(ValidationError):
            build_vision_detection_event(
                frame_index=0, model_id="m", detections=[_detection(bbox_norm=[0.1, 0.2, 0.3])]
            )

    def test_unknown_creature_category_raises(self):
        with pytest.raises(ValidationError):
            build_vision_detection_event(
                frame_index=0, model_id="m", detections=[_detection(creature_category="robot")]
            )

    def test_negative_frame_index_raises(self):
        with pytest.raises(ValidationError):
            build_vision_detection_event(frame_index=-1, model_id="m", detections=[])

    def test_result_can_be_buffered_via_collect_raw(self):
        event = build_vision_detection_event(
            frame_index=0, model_id="m", detections=[], device_id="rpi-camera-01"
        )
        collector = RpiTelemetryCollector()
        result = collector.collect_raw(event)
        assert result == event
        assert collector.buffer_size == 1
