"""Unit tests for telemetry/collector.py (Raspberry Pi telemetry module, PEN-166)."""

import json
import os
import tempfile
import uuid
from unittest.mock import patch

import pytest

from telemetry.collector import RpiTelemetryCollector, _generate_event_id, _utc_now_iso


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestGenerateEventId:
    def test_returns_uuid_string(self):
        eid = _generate_event_id()
        assert isinstance(eid, str)
        uuid.UUID(eid)  # raises ValueError if not a valid UUID

    def test_each_call_is_unique(self):
        ids = {_generate_event_id() for _ in range(50)}
        assert len(ids) == 50


class TestUtcNowIso:
    def test_ends_with_z(self):
        assert _utc_now_iso().endswith("Z")

    def test_matches_iso_pattern(self):
        import re
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", _utc_now_iso())


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_default_source_is_rpi(self):
        c = RpiTelemetryCollector()
        assert c.source == "rpi"

    def test_default_device_id(self):
        with patch.dict(os.environ, {}, clear=True):
            c = RpiTelemetryCollector()
            assert c.device_id == "rpi-camera-01"

    def test_device_id_from_env_var(self):
        with patch.dict(os.environ, {"RPI_DEVICE_ID": "rpi-test-42"}):
            c = RpiTelemetryCollector()
            assert c.device_id == "rpi-test-42"

    def test_explicit_device_id_overrides_env(self):
        with patch.dict(os.environ, {"RPI_DEVICE_ID": "rpi-test-42"}):
            c = RpiTelemetryCollector(device_id="explicit-id")
            assert c.device_id == "explicit-id"

    def test_session_id_auto_generated_as_uuid(self):
        c = RpiTelemetryCollector()
        uuid.UUID(c.session_id)

    def test_custom_session_id(self):
        c = RpiTelemetryCollector(session_id="my-session")
        assert c.session_id == "my-session"

    def test_empty_buffer_on_init(self):
        c = RpiTelemetryCollector()
        assert c.buffer_size == 0

    def test_dropped_count_zero_on_init(self):
        c = RpiTelemetryCollector()
        assert c.dropped_count == 0

    def test_invalid_count_zero_on_init(self):
        c = RpiTelemetryCollector()
        assert c.invalid_count == 0


# ---------------------------------------------------------------------------
# create_event
# ---------------------------------------------------------------------------

class TestCreateEvent:
    def test_includes_device_id_and_session_id(self):
        c = RpiTelemetryCollector(device_id="rpi-1", session_id="sess-1")
        event = c.create_event("device_status", {"device_name": "cam", "status": "connected"})
        assert event["device_id"] == "rpi-1"
        assert event["session_id"] == "sess-1"

    def test_required_keys_present(self):
        c = RpiTelemetryCollector()
        event = c.create_event("device_status", {"device_name": "cam", "status": "connected"})
        for key in ("event_id", "event_type", "source", "timestamp", "device_id", "session_id", "payload"):
            assert key in event

    def test_does_not_buffer_event(self):
        c = RpiTelemetryCollector()
        c.create_event("device_status", {"device_name": "cam", "status": "connected"})
        assert c.buffer_size == 0


# ---------------------------------------------------------------------------
# collect() / collect_raw()
# ---------------------------------------------------------------------------

class TestCollect:
    def test_valid_event_buffers_and_returns(self):
        c = RpiTelemetryCollector()
        event = c.collect("device_status", device_name="cam", status="connected")
        assert event is not None
        assert c.buffer_size == 1

    def test_invalid_event_dropped_and_counted(self):
        c = RpiTelemetryCollector()
        event = c.collect("device_status", device_name="cam", status="not_a_real_status")
        assert event is None
        assert c.buffer_size == 0
        assert c.invalid_count == 1

    def test_validate_false_skips_validation(self):
        c = RpiTelemetryCollector(validate=False)
        event = c.collect("device_status", device_name="cam", status="not_a_real_status")
        assert event is not None
        assert c.buffer_size == 1

    def test_collect_raw_buffers_prebuilt_event(self):
        c = RpiTelemetryCollector()
        prebuilt = c.create_event("connection_status", {"connected": True})
        result = c.collect_raw(prebuilt)
        assert result == prebuilt
        assert c.buffer_size == 1

    def test_collect_raw_rejects_invalid_event(self):
        c = RpiTelemetryCollector()
        bad_event = {"event_type": "connection_status"}  # missing required fields
        result = c.collect_raw(bad_event)
        assert result is None
        assert c.invalid_count == 1


# ---------------------------------------------------------------------------
# Buffer management - FIFO drop + overflow
# ---------------------------------------------------------------------------

class TestBufferManagement:
    def test_fifo_drop_when_buffer_full_no_overflow(self):
        c = RpiTelemetryCollector(max_buffer_size=3, overflow_path=None)
        for i in range(5):
            c.collect("connection_status", connected=True, seq=i)
        assert c.buffer_size == 3
        assert c.dropped_count == 2
        # Oldest events (seq 0, 1) were dropped; buffer holds seq 2, 3, 4.
        remaining_seqs = [e["payload"]["seq"] for e in c.peek()]
        assert remaining_seqs == [2, 3, 4]

    def test_overflow_persists_evicted_events_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "overflow.json")
            c = RpiTelemetryCollector(max_buffer_size=2, overflow_path=path)
            for i in range(4):
                c.collect("connection_status", connected=True, seq=i)
            assert c.buffer_size == 2
            assert os.path.exists(path)
            with open(path) as fh:
                lines = [json.loads(line) for line in fh if line.strip()]
            assert [e["payload"]["seq"] for e in lines] == [0, 1]

    def test_max_disk_bytes_caps_overflow_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "overflow.json")
            c = RpiTelemetryCollector(max_buffer_size=1, overflow_path=path, max_disk_bytes=1)
            for i in range(3):
                c.collect("connection_status", connected=True, seq=i)
            assert c.dropped_count >= 1

    def test_flush_returns_and_clears_buffer(self):
        c = RpiTelemetryCollector()
        c.collect("connection_status", connected=True)
        c.collect("connection_status", connected=False)
        events = c.flush()
        assert len(events) == 2
        assert c.buffer_size == 0

    def test_peek_does_not_clear_buffer(self):
        c = RpiTelemetryCollector()
        c.collect("connection_status", connected=True)
        events = c.peek()
        assert len(events) == 1
        assert c.buffer_size == 1

    def test_clear_discards_without_returning(self):
        c = RpiTelemetryCollector()
        c.collect("connection_status", connected=True)
        c.clear()
        assert c.buffer_size == 0


# ---------------------------------------------------------------------------
# Overflow load / clear
# ---------------------------------------------------------------------------

class TestOverflowLoadClear:
    def test_load_overflow_returns_persisted_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "overflow.json")
            c = RpiTelemetryCollector(max_buffer_size=1, overflow_path=path)
            for i in range(3):
                c.collect("connection_status", connected=True, seq=i)
            loaded = c.load_overflow()
            assert len(loaded) == 2

    def test_load_overflow_empty_when_no_file(self):
        c = RpiTelemetryCollector(overflow_path="/nonexistent/path/overflow.json")
        assert c.load_overflow() == []

    def test_clear_overflow_removes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "overflow.json")
            c = RpiTelemetryCollector(max_buffer_size=1, overflow_path=path)
            for i in range(3):
                c.collect("connection_status", connected=True, seq=i)
            assert os.path.exists(path)
            c.clear_overflow()
            assert not os.path.exists(path)

    def test_clear_overflow_safe_when_no_file(self):
        c = RpiTelemetryCollector(overflow_path="/nonexistent/path/overflow.json")
        c.clear_overflow()  # must not raise
