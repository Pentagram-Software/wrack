"""Unit tests for telemetry/schemas.py (Raspberry Pi telemetry module, PEN-166)."""

import uuid
from datetime import datetime, timezone

import pytest

from telemetry.schemas import (
    VALID_EVENT_TYPES,
    VALID_SOURCES,
    ValidationError,
    is_valid_event,
    validate_event,
    validate_payload,
)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uid() -> str:
    return str(uuid.uuid4())


def _base_event(event_type: str, payload: dict) -> dict:
    return {
        "event_id": _uid(),
        "event_type": event_type,
        "source": "rpi",
        "timestamp": _ts(),
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Envelope validation
# ---------------------------------------------------------------------------

class TestEnvelope:
    def test_valid_device_status_event_passes(self):
        event = _base_event("device_status", {"device_name": "cam", "status": "connected"})
        validate_event(event)  # should not raise

    def test_missing_event_id_rejected(self):
        event = _base_event("device_status", {"device_name": "cam", "status": "connected"})
        del event["event_id"]
        with pytest.raises(ValidationError):
            validate_event(event)

    def test_non_uuid_event_id_rejected(self):
        event = _base_event("device_status", {"device_name": "cam", "status": "connected"})
        event["event_id"] = "not-a-uuid"
        with pytest.raises(ValidationError):
            validate_event(event)

    def test_unknown_event_type_rejected(self):
        event = _base_event("something_unknown", {})
        with pytest.raises(ValidationError):
            validate_event(event)

    def test_ev3_source_rejected(self):
        """This module is scoped to the Raspberry Pi only."""
        event = _base_event("device_status", {"device_name": "cam", "status": "connected"})
        event["source"] = "ev3"
        with pytest.raises(ValidationError):
            validate_event(event)

    def test_bad_timestamp_rejected(self):
        event = _base_event("device_status", {"device_name": "cam", "status": "connected"})
        event["timestamp"] = "not-a-timestamp"
        with pytest.raises(ValidationError):
            validate_event(event)

    def test_non_dict_payload_rejected(self):
        event = _base_event("device_status", {"device_name": "cam", "status": "connected"})
        event["payload"] = "not-a-dict"
        with pytest.raises(ValidationError):
            validate_event(event)

    def test_device_id_and_session_id_optional(self):
        event = _base_event("device_status", {"device_name": "cam", "status": "connected"})
        validate_event(event)  # no device_id/session_id at all - should pass

    def test_device_id_and_session_id_accepted_when_strings(self):
        event = _base_event("device_status", {"device_name": "cam", "status": "connected"})
        event["device_id"] = "rpi-camera-01"
        event["session_id"] = _uid()
        validate_event(event)

    def test_non_string_device_id_rejected(self):
        event = _base_event("device_status", {"device_name": "cam", "status": "connected"})
        event["device_id"] = 12345
        with pytest.raises(ValidationError):
            validate_event(event)

    def test_is_valid_event_true_for_valid(self):
        event = _base_event("device_status", {"device_name": "cam", "status": "connected"})
        assert is_valid_event(event) is True

    def test_is_valid_event_false_for_invalid(self):
        assert is_valid_event({"not": "an event"}) is False

    def test_valid_sources_is_rpi_only(self):
        assert VALID_SOURCES == ["rpi"]

    def test_valid_event_types_includes_vision_detection(self):
        assert "vision_detection" in VALID_EVENT_TYPES


# ---------------------------------------------------------------------------
# video_stream_start
# ---------------------------------------------------------------------------

class TestVideoStreamStart:
    def _payload(self, **overrides):
        payload = {
            "protocol": "udp",
            "port": 9999,
            "resolution_width": 1280,
            "resolution_height": 720,
            "target_fps": 30,
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_passes(self):
        validate_payload("video_stream_start", self._payload())

    def test_optional_bitrate_accepted(self):
        validate_payload("video_stream_start", self._payload(bitrate=4_000_000))

    def test_invalid_protocol_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("video_stream_start", self._payload(protocol="ftp"))

    def test_invalid_port_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("video_stream_start", self._payload(port=70000))

    def test_negative_resolution_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("video_stream_start", self._payload(resolution_width=-1))


# ---------------------------------------------------------------------------
# video_stream_stop
# ---------------------------------------------------------------------------

class TestVideoStreamStop:
    def test_minimal_payload_passes(self):
        validate_payload("video_stream_stop", {"reason": "keyboard_interrupt"})

    def test_full_payload_passes(self):
        validate_payload(
            "video_stream_stop",
            {
                "reason": "keyboard_interrupt",
                "uptime_seconds": 60.0,
                "total_frames_sent": 1800,
                "total_frame_drops": 3,
            },
        )

    def test_missing_reason_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("video_stream_stop", {})

    def test_negative_total_frame_drops_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload(
                "video_stream_stop",
                {"reason": "x", "total_frame_drops": -1},
            )


# ---------------------------------------------------------------------------
# video_stream_health
# ---------------------------------------------------------------------------

class TestVideoStreamHealth:
    def _payload(self, **overrides):
        payload = {
            "fps_recent": 29.5,
            "client_count": 2,
            "frame_drop_total": 3,
            "uptime_seconds": 60.0,
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_passes(self):
        validate_payload("video_stream_health", self._payload())

    def test_optional_interval_seconds_accepted(self):
        validate_payload("video_stream_health", self._payload(interval_seconds=10.0))

    def test_negative_client_count_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("video_stream_health", self._payload(client_count=-1))


# ---------------------------------------------------------------------------
# device_status / connection_status / error
# ---------------------------------------------------------------------------

class TestDeviceStatus:
    def test_valid_payload_passes(self):
        validate_payload("device_status", {"device_name": "camera", "status": "connected"})

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("device_status", {"device_name": "camera", "status": "sleeping"})

    def test_camera_device_type_accepted(self):
        validate_payload(
            "device_status",
            {"device_name": "camera", "status": "connected", "device_type": "camera"},
        )


class TestConnectionStatus:
    def test_valid_payload_passes(self):
        validate_payload("connection_status", {"connected": True})

    def test_non_bool_connected_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("connection_status", {"connected": "yes"})


class TestErrorPayload:
    def test_valid_payload_passes(self):
        validate_payload("error", {"error_type": "camera_failure", "message": "no such device"})

    def test_missing_message_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("error", {"error_type": "camera_failure"})


# ---------------------------------------------------------------------------
# vision_detection (PEN-169)
# ---------------------------------------------------------------------------

class TestVisionDetection:
    def _detection(self, **overrides):
        detection = {
            "label": "cat",
            "creature_category": "animal",
            "confidence": 0.91,
            "bbox_norm": [0.12, 0.34, 0.45, 0.78],
        }
        detection.update(overrides)
        return detection

    def _payload(self, detections=None, **overrides):
        detections = self._detection() and [self._detection()] if detections is None else detections
        payload = {
            "frame_index": 4821,
            "model_id": "yolov8n-wrack",
            "detections": detections,
            "detection_count": len(detections),
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_with_detection_passes(self):
        validate_payload("vision_detection", self._payload())

    def test_empty_detections_passes(self):
        validate_payload("vision_detection", self._payload(detections=[]))

    def test_full_optional_fields_pass(self):
        validate_payload(
            "vision_detection",
            self._payload(
                inference_latency_ms=87.4,
                model_version="1.2.0",
                analysis_fps=4.9,
                scene_summary="cat, center; high confidence",
            ),
        )

    def test_track_id_accepted(self):
        validate_payload("vision_detection", self._payload(detections=[self._detection(track_id=3)]))

    def test_missing_model_id_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("vision_detection", {"frame_index": 0, "detections": [], "detection_count": 0})

    def test_negative_frame_index_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("vision_detection", self._payload(frame_index=-1))

    def test_detection_count_mismatch_rejected(self):
        payload = self._payload()
        payload["detection_count"] = 99
        with pytest.raises(ValidationError):
            validate_payload("vision_detection", payload)

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("vision_detection", self._payload(detections=[self._detection(confidence=1.5)]))

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload("vision_detection", self._payload(detections=[self._detection(confidence=-0.1)]))

    def test_bbox_with_three_elements_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload(
                "vision_detection",
                self._payload(detections=[self._detection(bbox_norm=[0.1, 0.2, 0.3])]),
            )

    def test_bbox_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload(
                "vision_detection",
                self._payload(detections=[self._detection(bbox_norm=[0.1, 0.2, 0.3, 1.5])]),
            )

    def test_unknown_creature_category_rejected(self):
        with pytest.raises(ValidationError):
            validate_payload(
                "vision_detection",
                self._payload(detections=[self._detection(creature_category="robot")]),
            )

    def test_missing_label_rejected(self):
        detection = self._detection()
        del detection["label"]
        with pytest.raises(ValidationError):
            validate_payload("vision_detection", self._payload(detections=[detection]))
