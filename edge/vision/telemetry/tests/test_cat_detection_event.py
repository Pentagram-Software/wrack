"""Unit tests for the cat_detection event builder + schema (PEN-193)."""

import uuid

import pytest

from telemetry.builder import build_cat_detection_event
from telemetry.schemas import ValidationError, validate_event


def _event(**overrides):
    kwargs = {
        "event_start_time": "2026-08-01T12:00:00Z",
        "event_end_time": "2026-08-01T12:00:45Z",
        "detection_confidence": 0.92,
        "device_id": "rpi-camera-01",
        "model_version": "yolov8n-1.0.0",
        "pipeline_version": "edge-vision-0.1.0",
    }
    kwargs.update(overrides)
    return build_cat_detection_event(**kwargs)


class TestBuildCatDetectionEvent:
    def test_defaults_to_unknown_identity_and_null_identification_confidence(self):
        event = _event()
        payload = event["payload"]
        assert payload["predicted_identity"] == "unknown"
        assert payload["final_identity"] == "unknown"
        assert payload["identification_confidence"] is None

    def test_event_type_and_routing_type_are_event(self):
        event = _event()
        assert event["event_type"] == "cat_detection"
        assert event["type"] == "event"

    def test_event_id_is_valid_uuid_by_default(self):
        event = _event()
        uuid.UUID(event["event_id"])

    def test_explicit_event_id_is_preserved(self):
        fixed_id = str(uuid.uuid4())
        event = _event(event_id=fixed_id)
        assert event["event_id"] == fixed_id

    def test_retrying_with_same_event_id_produces_identical_id_for_dedup(self):
        """Mirrors RpiTelemetrySender's use of event_id as the BigQuery
        insertId dedup key (see telemetry/sender.py) — a caller that rebuilds
        the same logical event for a retry, passing the first build's
        event_id back in, must get that same id out again."""
        first = _event()
        retried = _event(event_id=first["event_id"])
        assert retried["event_id"] == first["event_id"]

    def test_phase2_real_identity_is_forwarded(self):
        event = _event(
            predicted_identity="ryfka",
            final_identity="ryfka",
            identification_confidence=0.87,
        )
        payload = event["payload"]
        assert payload["predicted_identity"] == "ryfka"
        assert payload["final_identity"] == "ryfka"
        assert payload["identification_confidence"] == 0.87

    def test_below_threshold_identification_keeps_predicted_but_falls_back_final(self):
        event = _event(
            predicted_identity="chaja",
            final_identity="unknown",
            identification_confidence=0.31,
        )
        payload = event["payload"]
        assert payload["predicted_identity"] == "chaja"
        assert payload["final_identity"] == "unknown"

    def test_open_event_end_time_none_is_allowed(self):
        event = _event(event_end_time=None)
        assert event["payload"]["event_end_time"] is None

    def test_device_id_forwarded_to_envelope_and_payload(self):
        event = _event(device_id="rpi-camera-02")
        assert event["device_id"] == "rpi-camera-02"
        assert event["payload"]["device_id"] == "rpi-camera-02"

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            _event(detection_confidence=1.5)

    def test_invalid_identity_raises(self):
        with pytest.raises(ValidationError):
            _event(predicted_identity="mittens")

    def test_malformed_start_time_raises(self):
        with pytest.raises(ValidationError):
            _event(event_start_time="not-a-timestamp")

    def test_blank_device_id_raises(self):
        with pytest.raises(ValidationError):
            _event(device_id="")

    def test_result_round_trips_through_validate_event(self):
        """The built event must also pass standalone re-validation, the way
        a caller loading it back from disk (e.g. the sender's overflow file)
        would validate it again."""
        event = _event()
        validate_event(event)  # must not raise
