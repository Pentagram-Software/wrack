"""Unit tests for telemetry/collector.py."""

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from telemetry.collector import TelemetryCollector, _generate_event_id, _utc_now_iso


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# _generate_event_id
# ---------------------------------------------------------------------------

class TestGenerateEventId:
    def test_returns_string(self):
        assert isinstance(_generate_event_id(), str)

    def test_looks_like_uuid(self):
        eid = _generate_event_id()
        parts = eid.split("-")
        assert len(parts) == 5, f"Expected UUID shape, got {eid!r}"

    def test_each_call_is_unique(self):
        ids = {_generate_event_id() for _ in range(50)}
        assert len(ids) == 50


# ---------------------------------------------------------------------------
# _utc_now_iso
# ---------------------------------------------------------------------------

class TestUtcNowIso:
    def test_returns_string(self):
        assert isinstance(_utc_now_iso(), str)

    def test_ends_with_z(self):
        assert _utc_now_iso().endswith("Z")

    def test_matches_iso_pattern(self):
        import re
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
        assert pattern.match(_utc_now_iso()), f"Timestamp {_utc_now_iso()!r} does not match ISO 8601"

    def test_falls_back_to_gmtime_when_datetime_unavailable(self):
        fake_time = type("FakeTime", (), {
            "time": staticmethod(lambda: 1700000000),
            "gmtime": staticmethod(lambda _epoch: (2023, 11, 14, 22, 13, 20, 1, 318)),
        })()
        with patch("telemetry.collector._HAS_DATETIME", False), \
             patch("telemetry.collector._HAS_TIME", True), \
             patch("telemetry.collector._time", fake_time):
            assert _utc_now_iso() == "2023-11-14T22:13:20Z"


# ---------------------------------------------------------------------------
# TelemetryCollector — construction
# ---------------------------------------------------------------------------

class TestTelemetryCollectorInit:
    def test_default_source_is_ev3(self):
        c = TelemetryCollector()
        assert c.source == "ev3"

    def test_custom_source(self):
        c = TelemetryCollector(source="rpi")
        assert c.source == "rpi"

    def test_empty_buffer_on_init(self):
        c = TelemetryCollector()
        assert c.buffer_size == 0

    def test_dropped_count_zero_on_init(self):
        c = TelemetryCollector()
        assert c.dropped_count == 0


# ---------------------------------------------------------------------------
# create_event
# ---------------------------------------------------------------------------

class TestCreateEvent:
    def test_returns_dict_with_required_keys(self):
        c = TelemetryCollector()
        event = c.create_event("battery_status", {"voltage_mv": 7000, "percentage": 80.0})
        for key in ("event_id", "event_type", "source", "timestamp", "payload"):
            assert key in event, f"Missing key: {key}"

    def test_event_type_set_correctly(self):
        c = TelemetryCollector()
        event = c.create_event("error", {"error_type": "hw", "message": "motor stall"})
        assert event["event_type"] == "error"

    def test_source_defaults_to_collector_source(self):
        c = TelemetryCollector(source="rpi")
        event = c.create_event("device_status", {"device_name": "motor", "status": "connected"})
        assert event["source"] == "rpi"

    def test_source_override(self):
        c = TelemetryCollector(source="ev3")
        event = c.create_event("device_status", {"device_name": "m", "status": "connected"}, source="cloud_functions")
        assert event["source"] == "cloud_functions"

    def test_event_id_override(self):
        c = TelemetryCollector()
        custom_id = _uid()
        event = c.create_event("battery_status", {"voltage_mv": 7000, "percentage": 80.0}, event_id=custom_id)
        assert event["event_id"] == custom_id

    def test_timestamp_override(self):
        c = TelemetryCollector()
        ts = "2026-01-15T12:00:00Z"
        event = c.create_event("battery_status", {"voltage_mv": 7000, "percentage": 80.0}, timestamp=ts)
        assert event["timestamp"] == ts

    def test_payload_stored_as_given(self):
        c = TelemetryCollector()
        payload = {"voltage_mv": 7200, "percentage": 90.0, "is_critical": False}
        event = c.create_event("battery_status", payload)
        assert event["payload"] == payload

    def test_does_not_buffer_event(self):
        c = TelemetryCollector()
        c.create_event("battery_status", {"voltage_mv": 7000, "percentage": 80.0})
        assert c.buffer_size == 0


# ---------------------------------------------------------------------------
# collect_battery_status
# ---------------------------------------------------------------------------

class TestCollectBatteryStatus:
    def test_returns_valid_event(self):
        c = TelemetryCollector()
        event = c.collect_battery_status(voltage_mv=7500, percentage=92.0)
        assert event["event_type"] == "battery_status"
        assert event["payload"]["voltage_mv"] == 7500
        assert event["payload"]["percentage"] == 92.0

    def test_buffers_event(self):
        c = TelemetryCollector()
        c.collect_battery_status(voltage_mv=7500, percentage=92.0)
        assert c.buffer_size == 1

    def test_optional_voltage_v(self):
        c = TelemetryCollector()
        event = c.collect_battery_status(7500, 92.0, voltage_v=7.5)
        assert event["payload"]["voltage_v"] == 7.5

    def test_optional_is_critical(self):
        c = TelemetryCollector()
        event = c.collect_battery_status(6000, 10.0, is_critical=True)
        assert event["payload"]["is_critical"] is True

    def test_optional_battery_type(self):
        c = TelemetryCollector()
        event = c.collect_battery_status(7200, 85.0, battery_type="rechargeable")
        assert event["payload"]["battery_type"] == "rechargeable"

    def test_omitted_optionals_not_in_payload(self):
        c = TelemetryCollector()
        event = c.collect_battery_status(7200, 85.0)
        payload = event["payload"]
        assert "voltage_v" not in payload
        assert "is_critical" not in payload
        assert "battery_type" not in payload

    def test_event_passes_schema_validation(self):
        from telemetry.schemas import validate_event
        c = TelemetryCollector()
        event = c.collect_battery_status(7200, 85.0)
        validate_event(event)  # should not raise


# ---------------------------------------------------------------------------
# collect_command_received
# ---------------------------------------------------------------------------

class TestCollectCommandReceived:
    def test_returns_valid_event(self):
        c = TelemetryCollector()
        event = c.collect_command_received("forward")
        assert event["event_type"] == "command_received"
        assert event["payload"]["command"] == "forward"

    def test_buffers_event(self):
        c = TelemetryCollector()
        c.collect_command_received("stop")
        assert c.buffer_size == 1

    def test_optional_controller_type(self):
        c = TelemetryCollector()
        event = c.collect_command_received("backward", controller_type="ps4")
        assert event["payload"]["controller_type"] == "ps4"

    def test_optional_params(self):
        c = TelemetryCollector()
        event = c.collect_command_received("drive", params={"speed": 500})
        assert event["payload"]["params"] == {"speed": 500}

    def test_event_passes_schema_validation(self):
        from telemetry.schemas import validate_event
        c = TelemetryCollector()
        event = c.collect_command_received("forward")
        validate_event(event)


# ---------------------------------------------------------------------------
# collect_command_executed
# ---------------------------------------------------------------------------

class TestCollectCommandExecuted:
    def test_returns_valid_event(self):
        c = TelemetryCollector()
        event = c.collect_command_executed("forward", success=True)
        assert event["event_type"] == "command_executed"
        assert event["payload"]["command"] == "forward"
        assert event["payload"]["success"] is True

    def test_failed_command(self):
        c = TelemetryCollector()
        event = c.collect_command_executed("turret", success=False)
        assert event["payload"]["success"] is False

    def test_optional_duration_ms(self):
        c = TelemetryCollector()
        event = c.collect_command_executed("forward", True, duration_ms=150.5)
        assert event["payload"]["duration_ms"] == 150.5

    def test_optional_error_message(self):
        c = TelemetryCollector()
        event = c.collect_command_executed("turret", False, error_message="stalled")
        assert event["payload"]["error_message"] == "stalled"

    def test_event_passes_schema_validation(self):
        from telemetry.schemas import validate_event
        c = TelemetryCollector()
        event = c.collect_command_executed("forward", True)
        validate_event(event)


# ---------------------------------------------------------------------------
# collect_device_status
# ---------------------------------------------------------------------------

class TestCollectDeviceStatus:
    def test_returns_valid_event(self):
        c = TelemetryCollector()
        event = c.collect_device_status("drive_L_motor", "connected")
        assert event["event_type"] == "device_status"
        assert event["payload"]["device_name"] == "drive_L_motor"
        assert event["payload"]["status"] == "connected"

    def test_optional_device_type(self):
        c = TelemetryCollector()
        event = c.collect_device_status("gyro", "error", device_type="sensor")
        assert event["payload"]["device_type"] == "sensor"

    def test_optional_port(self):
        c = TelemetryCollector()
        event = c.collect_device_status("motor", "initializing", port="A")
        assert event["payload"]["port"] == "A"

    def test_event_passes_schema_validation(self):
        from telemetry.schemas import validate_event
        c = TelemetryCollector()
        event = c.collect_device_status("us_sensor", "connected")
        validate_event(event)


# ---------------------------------------------------------------------------
# collect_error
# ---------------------------------------------------------------------------

class TestCollectError:
    def test_returns_valid_event(self):
        c = TelemetryCollector()
        event = c.collect_error("MotorStall", "Drive motor A stalled")
        assert event["event_type"] == "error"
        assert event["payload"]["error_type"] == "MotorStall"
        assert event["payload"]["message"] == "Drive motor A stalled"

    def test_optional_stack_trace(self):
        c = TelemetryCollector()
        event = c.collect_error("RuntimeError", "oops", stack_trace="Traceback...")
        assert event["payload"]["stack_trace"] == "Traceback..."

    def test_optional_context(self):
        c = TelemetryCollector()
        event = c.collect_error("RuntimeError", "oops", context={"motor": "A"})
        assert event["payload"]["context"] == {"motor": "A"}

    def test_event_passes_schema_validation(self):
        from telemetry.schemas import validate_event
        c = TelemetryCollector()
        event = c.collect_error("IOError", "sensor read failed")
        validate_event(event)


# ---------------------------------------------------------------------------
# collect_connection_status
# ---------------------------------------------------------------------------

class TestCollectConnectionStatus:
    def test_returns_valid_event(self):
        c = TelemetryCollector()
        event = c.collect_connection_status(connected=True)
        assert event["event_type"] == "connection_status"
        assert event["payload"]["connected"] is True

    def test_disconnected(self):
        c = TelemetryCollector()
        event = c.collect_connection_status(False, host="192.168.1.10", error_message="timeout")
        assert event["payload"]["connected"] is False
        assert event["payload"]["host"] == "192.168.1.10"
        assert event["payload"]["error_message"] == "timeout"

    def test_buffers_event(self):
        c = TelemetryCollector()
        c.collect_connection_status(True)
        assert c.buffer_size == 1


# ---------------------------------------------------------------------------
# Buffer management
# ---------------------------------------------------------------------------

class TestBufferManagement:
    def test_buffer_size_increments(self):
        c = TelemetryCollector()
        for i in range(5):
            c.collect_battery_status(7000 + i * 10, float(50 + i))
        assert c.buffer_size == 5

    def test_flush_returns_all_events(self):
        c = TelemetryCollector()
        c.collect_battery_status(7000, 80.0)
        c.collect_command_received("stop")
        events = c.flush()
        assert len(events) == 2

    def test_flush_clears_buffer(self):
        c = TelemetryCollector()
        c.collect_battery_status(7000, 80.0)
        c.flush()
        assert c.buffer_size == 0

    def test_peek_does_not_clear_buffer(self):
        c = TelemetryCollector()
        c.collect_battery_status(7000, 80.0)
        events = c.peek()
        assert len(events) == 1
        assert c.buffer_size == 1

    def test_clear_empties_buffer(self):
        c = TelemetryCollector()
        c.collect_battery_status(7000, 80.0)
        c.clear()
        assert c.buffer_size == 0

    def test_buffer_overflow_evicts_oldest(self):
        c = TelemetryCollector(max_buffer_size=3, overflow_path=None)
        for i in range(5):
            c.collect_battery_status(7000 + i, float(i * 10))
        assert c.buffer_size == 3
        # Most recent 3 remain
        events = c.peek()
        assert events[-1]["payload"]["voltage_mv"] == 7004

    def test_dropped_count_increments_when_overflow_disabled(self):
        c = TelemetryCollector(max_buffer_size=2, overflow_path=None)
        for i in range(5):
            c.collect_battery_status(7000 + i, float(i * 10))
        assert c.dropped_count == 3

    def test_overflow_written_to_disk(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            c = TelemetryCollector(max_buffer_size=2, overflow_path=path)
            os.remove(path)  # start fresh
            for i in range(4):
                c.collect_battery_status(7000 + i, float(i * 10))
            assert os.path.exists(path)
            overflow = c.load_overflow()
            assert len(overflow) == 2
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_clear_overflow_deletes_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            c = TelemetryCollector(max_buffer_size=1, overflow_path=path)
            os.remove(path)
            c.collect_battery_status(7000, 80.0)
            c.collect_battery_status(7001, 81.0)  # triggers overflow write
            assert os.path.exists(path)
            c.clear_overflow()
            assert not os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_load_overflow_returns_empty_when_no_file(self):
        c = TelemetryCollector(overflow_path="/tmp/nonexistent_wrack_test.json")
        result = c.load_overflow()
        assert result == []

    def test_large_event_does_not_exceed_disk_cap(self):
        """A single oversized event must be dropped, not pushed past the cap."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            os.remove(path)
            # Tiny cap so one event already exceeds it.
            c = TelemetryCollector(
                max_buffer_size=1, overflow_path=path, max_disk_bytes=50
            )
            c.collect_battery_status(7000, 80.0)
            c.collect_battery_status(7001, 81.0)  # evicts the first -> persist
            # Event JSON is well over 50 bytes, so it is dropped before writing.
            assert c.dropped_count == 1
            file_size = os.path.getsize(path) if os.path.exists(path) else 0
            assert file_size <= 50
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_persist_tolerates_open_without_encoding_kwarg(self):
        """MicroPython's open() has no encoding kwarg; persistence must not crash."""
        import builtins

        real_open = builtins.open

        def micropython_open(*args, **kwargs):
            # Emulate Pybricks/MicroPython: reject the CPython-only encoding kwarg.
            if "encoding" in kwargs:
                raise TypeError(
                    "open() got an unexpected keyword argument 'encoding'"
                )
            return real_open(*args, **kwargs)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            os.remove(path)
            c = TelemetryCollector(max_buffer_size=1, overflow_path=path)
            with patch("builtins.open", side_effect=micropython_open):
                c.collect_battery_status(7000, 80.0)
                c.collect_battery_status(7001, 81.0)  # triggers overflow write
            # The evicted event was persisted via the no-encoding fallback,
            # so nothing was dropped and the file exists.
            assert c.dropped_count == 0
            assert os.path.exists(path)
            with patch("builtins.open", side_effect=micropython_open):
                overflow = c.load_overflow()
            assert len(overflow) == 1
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_multiple_events_in_buffer_order(self):
        c = TelemetryCollector()
        e1 = c.collect_command_received("forward")
        e2 = c.collect_command_received("stop")
        events = c.flush()
        assert events[0]["event_id"] == e1["event_id"]
        assert events[1]["event_id"] == e2["event_id"]


# ---------------------------------------------------------------------------
# Generic collect() API + invalid_count (PEN-121 graft)
# ---------------------------------------------------------------------------

class TestGenericCollect:
    def test_initial_invalid_count_zero(self):
        assert TelemetryCollector().invalid_count == 0

    def test_valid_event_returns_dict(self):
        c = TelemetryCollector()
        event = c.collect("battery_status", voltage_mv=7500, percentage=90.0)
        assert event is not None
        assert event["event_type"] == "battery_status"

    def test_valid_event_is_buffered(self):
        c = TelemetryCollector()
        c.collect("battery_status", voltage_mv=7500, percentage=90.0)
        assert c.buffer_size == 1

    def test_payload_matches_kwargs(self):
        c = TelemetryCollector()
        event = c.collect("battery_status", voltage_mv=6800, percentage=45.0)
        assert event["payload"] == {"voltage_mv": 6800, "percentage": 45.0}

    def test_event_id_is_uuid_shaped(self):
        c = TelemetryCollector()
        event = c.collect("battery_status", voltage_mv=7500, percentage=90.0)
        assert len(event["event_id"].split("-")) == 5

    def test_timestamp_ends_with_z(self):
        c = TelemetryCollector()
        event = c.collect("battery_status", voltage_mv=7500, percentage=90.0)
        assert event["timestamp"].endswith("Z")

    def test_source_defaults_to_ev3(self):
        c = TelemetryCollector()
        event = c.collect("battery_status", voltage_mv=7500, percentage=90.0)
        assert event["source"] == "ev3"

    def test_invalid_payload_returns_none(self):
        c = TelemetryCollector()
        assert c.collect("battery_status", voltage_mv=-1, percentage=200) is None

    def test_invalid_payload_increments_invalid_count(self):
        c = TelemetryCollector()
        c.collect("battery_status", voltage_mv=-1, percentage=200)
        assert c.invalid_count == 1

    def test_invalid_payload_not_buffered(self):
        c = TelemetryCollector()
        c.collect("battery_status", voltage_mv=-1, percentage=200)
        assert c.buffer_size == 0

    def test_multiple_invalid_events_accumulate(self):
        c = TelemetryCollector()
        for _ in range(5):
            c.collect("battery_status", voltage_mv=-1, percentage=999)
        assert c.invalid_count == 5

    def test_unknown_event_type_rejected_when_validating(self):
        c = TelemetryCollector()
        assert c.collect("nonexistent_type", foo="bar") is None
        assert c.invalid_count == 1

    def test_validate_false_skips_validation(self):
        c = TelemetryCollector(validate=False)
        event = c.collect("nonexistent_type", bogus_field=True)
        assert event is not None
        assert c.buffer_size == 1
        assert c.invalid_count == 0

    def test_collect_does_not_affect_typed_helpers(self):
        c = TelemetryCollector()
        c.collect("battery_status", voltage_mv=7500, percentage=90.0)
        c.collect_command_received("forward")
        assert c.buffer_size == 2
