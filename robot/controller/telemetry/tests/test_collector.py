"""Unit tests for robot/controller/telemetry/collector.py.

Coverage target: >80% of collector.py lines.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from telemetry.collector import TelemetryCollector, _new_uuid, _utc_now_iso


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z$")


def _battery_data(**overrides):
    data = {"voltage_mv": 7200, "percentage": 85.0}
    data.update(overrides)
    return data


def _command_received_data(**overrides):
    data = {"command": "forward"}
    data.update(overrides)
    return data


def _command_executed_data(**overrides):
    data = {"command": "forward", "success": True}
    data.update(overrides)
    return data


def _device_status_data(**overrides):
    data = {"device_name": "drive_L", "status": "connected"}
    data.update(overrides)
    return data


def _error_data(**overrides):
    data = {"error_type": "device_error", "message": "Motor stalled"}
    data.update(overrides)
    return data


@pytest.fixture
def collector():
    """A default TelemetryCollector for testing."""
    return TelemetryCollector()


@pytest.fixture
def identified_collector():
    """Collector with session/device IDs."""
    return TelemetryCollector(
        source="ev3",
        session_id="sess-abc123",
        device_id="ev3-unit-1",
    )


@pytest.fixture
def spill_file(tmp_path):
    """Temporary path for disk spill tests."""
    return str(tmp_path / "spill" / "telemetry_overflow.jsonl")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_new_uuid_format(self):
        uid = _new_uuid()
        assert UUID_RE.match(uid), f"Not a valid UUID: {uid}"

    def test_new_uuid_uniqueness(self):
        uids = {_new_uuid() for _ in range(100)}
        assert len(uids) == 100

    def test_utc_now_iso_format(self):
        ts = _utc_now_iso()
        assert ISO8601_RE.match(ts), f"Bad timestamp: {ts}"

    def test_utc_now_iso_ends_with_z(self):
        assert _utc_now_iso().endswith("Z")

    def test_utc_now_iso_includes_milliseconds(self):
        ts = _utc_now_iso()
        # Expect fractional seconds portion
        assert "." in ts


# ---------------------------------------------------------------------------
# Constructor / properties
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_defaults(self, collector):
        assert collector.source == "ev3"
        assert collector.session_id is None
        assert collector.device_id is None
        assert collector.max_buffer == 500
        assert collector.disk_spill_path is None

    def test_custom_source(self):
        c = TelemetryCollector(source="rpi")
        assert c.source == "rpi"

    def test_session_and_device_ids(self):
        c = TelemetryCollector(session_id="s1", device_id="d1")
        assert c.session_id == "s1"
        assert c.device_id == "d1"

    def test_custom_max_buffer(self):
        c = TelemetryCollector(max_buffer=10)
        assert c.max_buffer == 10

    def test_disk_spill_path(self, spill_file):
        c = TelemetryCollector(disk_spill_path=spill_file)
        assert c.disk_spill_path == spill_file

    def test_initial_size_zero(self, collector):
        assert collector.size() == 0

    def test_initial_dropped_count_zero(self, collector):
        assert collector.dropped_count == 0

    def test_initial_invalid_count_zero(self, collector):
        assert collector.invalid_count == 0


# ---------------------------------------------------------------------------
# collect() — event envelope structure
# ---------------------------------------------------------------------------


class TestCollectEnvelope:
    def test_returns_event_dict(self, collector):
        event = collector.collect("battery_status", **_battery_data())
        assert isinstance(event, dict)

    def test_event_id_is_valid_uuid(self, collector):
        event = collector.collect("battery_status", **_battery_data())
        assert UUID_RE.match(event["event_id"]), f"Bad event_id: {event['event_id']}"

    def test_each_event_has_unique_id(self, collector):
        events = [collector.collect("battery_status", **_battery_data()) for _ in range(20)]
        ids = {e["event_id"] for e in events}
        assert len(ids) == 20

    def test_event_type_is_preserved(self, collector):
        event = collector.collect("battery_status", **_battery_data())
        assert event["event_type"] == "battery_status"

    def test_source_defaults_to_ev3(self, collector):
        event = collector.collect("battery_status", **_battery_data())
        assert event["source"] == "ev3"

    def test_source_custom(self):
        c = TelemetryCollector(source="rpi")
        event = c.collect("battery_status", **_battery_data())
        assert event["source"] == "rpi"

    def test_timestamp_is_iso8601(self, collector):
        event = collector.collect("battery_status", **_battery_data())
        assert ISO8601_RE.match(event["timestamp"]), f"Bad timestamp: {event['timestamp']}"

    def test_payload_matches_kwargs(self, collector):
        event = collector.collect("battery_status", voltage_mv=6800, percentage=45.0)
        assert event["payload"] == {"voltage_mv": 6800, "percentage": 45.0}

    def test_no_session_id_by_default(self, collector):
        event = collector.collect("battery_status", **_battery_data())
        assert "session_id" not in event

    def test_no_device_id_by_default(self, collector):
        event = collector.collect("battery_status", **_battery_data())
        assert "device_id" not in event

    def test_session_id_injected(self, identified_collector):
        event = identified_collector.collect("battery_status", **_battery_data())
        assert event["session_id"] == "sess-abc123"

    def test_device_id_injected(self, identified_collector):
        event = identified_collector.collect("battery_status", **_battery_data())
        assert event["device_id"] == "ev3-unit-1"

    def test_all_p0_event_types_accepted(self, collector):
        payloads = {
            "battery_status": _battery_data(),
            "command_received": _command_received_data(),
            "command_executed": _command_executed_data(),
            "device_status": _device_status_data(),
            "error": _error_data(),
        }
        for event_type, payload in payloads.items():
            event = collector.collect(event_type, **payload)
            assert event is not None, f"Expected event for {event_type}"
            assert event["event_type"] == event_type

    def test_non_p0_event_type_accepted(self):
        c = TelemetryCollector(validate=False)
        event = c.collect("motor_status", speed=100)
        assert event is not None
        assert event["event_type"] == "motor_status"


# ---------------------------------------------------------------------------
# collect() — validation
# ---------------------------------------------------------------------------


class TestCollectValidation:
    def test_invalid_event_returns_none(self, collector):
        # Missing required fields
        result = collector.collect("battery_status", voltage_mv=-1, percentage=200)
        assert result is None

    def test_invalid_event_increments_invalid_count(self, collector):
        collector.collect("battery_status", voltage_mv=-1, percentage=200)
        assert collector.invalid_count == 1

    def test_multiple_invalid_events_accumulate(self, collector):
        for _ in range(5):
            collector.collect("battery_status", voltage_mv=-999, percentage=999)
        assert collector.invalid_count == 5

    def test_invalid_event_not_buffered(self, collector):
        collector.collect("battery_status", voltage_mv=-1, percentage=200)
        assert collector.size() == 0

    def test_invalid_event_type_returns_none(self, collector):
        result = collector.collect("nonexistent_type", foo="bar")
        assert result is None

    def test_validate_false_skips_validation(self):
        c = TelemetryCollector(validate=False)
        # This would normally fail validation
        event = c.collect("nonexistent_type", bogus_field=True)
        assert event is not None
        assert event["event_type"] == "nonexistent_type"

    def test_validate_false_invalid_payload_still_buffered(self):
        c = TelemetryCollector(validate=False)
        event = c.collect("battery_status", voltage_mv=-999)
        assert event is not None
        assert c.size() == 1

    def test_validate_false_does_not_increment_invalid_count(self):
        c = TelemetryCollector(validate=False)
        c.collect("nonexistent_type", foo=True)
        assert c.invalid_count == 0

    def test_mixed_valid_and_invalid(self, collector):
        collector.collect("battery_status", **_battery_data())  # valid
        collector.collect("battery_status", voltage_mv=-1, percentage=200)  # invalid
        collector.collect("command_received", **_command_received_data())  # valid
        assert collector.size() == 2
        assert collector.invalid_count == 1


# ---------------------------------------------------------------------------
# Buffer management
# ---------------------------------------------------------------------------


class TestBufferManagement:
    def test_events_accumulate_in_buffer(self, collector):
        for i in range(5):
            collector.collect("battery_status", voltage_mv=7200 + i, percentage=80.0)
        assert collector.size() == 5

    def test_buffer_at_max_capacity(self):
        c = TelemetryCollector(max_buffer=3)
        for _ in range(3):
            c.collect("battery_status", **_battery_data())
        assert c.size() == 3

    def test_fifo_drop_on_overflow(self):
        c = TelemetryCollector(max_buffer=3, validate=False)
        # Collect 4 events; the first should be dropped
        first = c.collect("battery_status", voltage_mv=1000, percentage=10.0)
        c.collect("battery_status", voltage_mv=2000, percentage=20.0)
        c.collect("battery_status", voltage_mv=3000, percentage=30.0)
        c.collect("battery_status", voltage_mv=4000, percentage=40.0)  # triggers drop

        assert c.size() == 3
        events = c.get_events()
        # First event should have been dropped
        remaining_ids = {e["event_id"] for e in events}
        assert first["event_id"] not in remaining_ids

    def test_fifo_drop_order(self):
        c = TelemetryCollector(max_buffer=2, validate=False)
        e1 = c.collect("battery_status", voltage_mv=1000, percentage=10.0)
        e2 = c.collect("battery_status", voltage_mv=2000, percentage=20.0)
        e3 = c.collect("battery_status", voltage_mv=3000, percentage=30.0)

        events = c.get_events()
        ids = [e["event_id"] for e in events]
        assert e1["event_id"] not in ids
        assert e2["event_id"] in ids
        assert e3["event_id"] in ids

    def test_dropped_count_increments_on_overflow(self):
        c = TelemetryCollector(max_buffer=2)
        for _ in range(5):
            c.collect("battery_status", **_battery_data())
        assert c.dropped_count == 3

    def test_dropped_count_zero_when_no_overflow(self, collector):
        collector.collect("battery_status", **_battery_data())
        collector.collect("battery_status", **_battery_data())
        assert collector.dropped_count == 0

    def test_buffer_holds_exactly_max(self):
        max_buf = 10
        c = TelemetryCollector(max_buffer=max_buf)
        for i in range(max_buf * 2):
            c.collect("battery_status", voltage_mv=7000 + i, percentage=50.0)
        assert c.size() == max_buf


# ---------------------------------------------------------------------------
# get_events()
# ---------------------------------------------------------------------------


class TestGetEvents:
    def test_returns_empty_list_when_buffer_empty(self, collector):
        assert collector.get_events() == []

    def test_returns_all_events(self, collector):
        for _ in range(3):
            collector.collect("battery_status", **_battery_data())
        events = collector.get_events()
        assert len(events) == 3

    def test_does_not_clear_buffer(self, collector):
        collector.collect("battery_status", **_battery_data())
        collector.get_events()
        assert collector.size() == 1

    def test_returns_events_oldest_first(self):
        c = TelemetryCollector(validate=False)
        e1 = c.collect("battery_status", voltage_mv=1000, percentage=10.0)
        e2 = c.collect("battery_status", voltage_mv=2000, percentage=20.0)
        events = c.get_events()
        assert events[0]["event_id"] == e1["event_id"]
        assert events[1]["event_id"] == e2["event_id"]

    def test_limit_returns_only_n_events(self, collector):
        for _ in range(10):
            collector.collect("battery_status", **_battery_data())
        events = collector.get_events(limit=3)
        assert len(events) == 3

    def test_limit_larger_than_buffer_returns_all(self, collector):
        for _ in range(5):
            collector.collect("battery_status", **_battery_data())
        events = collector.get_events(limit=100)
        assert len(events) == 5

    def test_limit_zero_returns_empty(self, collector):
        collector.collect("battery_status", **_battery_data())
        events = collector.get_events(limit=0)
        assert events == []

    def test_returns_copies_not_originals(self, collector):
        collector.collect("battery_status", **_battery_data())
        events1 = collector.get_events()
        events2 = collector.get_events()
        # Should return equal dicts but the list itself is a fresh snapshot
        assert events1 == events2
        assert events1 is not events2


# ---------------------------------------------------------------------------
# flush()
# ---------------------------------------------------------------------------


class TestFlush:
    def test_flush_returns_all_events(self, collector):
        for _ in range(5):
            collector.collect("battery_status", **_battery_data())
        events = collector.flush()
        assert len(events) == 5

    def test_flush_clears_buffer(self, collector):
        for _ in range(5):
            collector.collect("battery_status", **_battery_data())
        collector.flush()
        assert collector.size() == 0

    def test_flush_returns_empty_when_buffer_empty(self, collector):
        assert collector.flush() == []

    def test_flush_then_collect_again(self, collector):
        collector.collect("battery_status", **_battery_data())
        collector.flush()
        collector.collect("battery_status", **_battery_data())
        assert collector.size() == 1

    def test_flush_returns_oldest_first(self):
        c = TelemetryCollector(validate=False)
        e1 = c.collect("battery_status", voltage_mv=1000, percentage=10.0)
        e2 = c.collect("battery_status", voltage_mv=2000, percentage=20.0)
        events = c.flush()
        assert events[0]["event_id"] == e1["event_id"]
        assert events[1]["event_id"] == e2["event_id"]


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_empties_buffer(self, collector):
        for _ in range(5):
            collector.collect("battery_status", **_battery_data())
        collector.clear()
        assert collector.size() == 0

    def test_clear_on_empty_buffer(self, collector):
        collector.clear()  # should not raise
        assert collector.size() == 0

    def test_clear_does_not_reset_dropped_count(self):
        c = TelemetryCollector(max_buffer=1)
        c.collect("battery_status", **_battery_data())
        c.collect("battery_status", **_battery_data())  # triggers drop
        c.clear()
        assert c.dropped_count == 1


# ---------------------------------------------------------------------------
# Disk spill
# ---------------------------------------------------------------------------


class TestDiskSpill:
    def test_spill_file_created_on_overflow(self, spill_file):
        c = TelemetryCollector(max_buffer=1, disk_spill_path=spill_file)
        c.collect("battery_status", **_battery_data())
        c.collect("battery_status", **_battery_data())  # triggers spill

        assert os.path.exists(spill_file), "Spill file not created"

    def test_spill_file_contains_json_line(self, spill_file):
        c = TelemetryCollector(max_buffer=1, disk_spill_path=spill_file)
        first = c.collect("battery_status", **_battery_data())
        c.collect("battery_status", voltage_mv=6000, percentage=30.0)  # triggers spill

        with open(spill_file, encoding="utf-8") as fh:
            lines = fh.readlines()

        assert len(lines) == 1
        spilled = json.loads(lines[0])
        assert spilled["event_id"] == first["event_id"]

    def test_spill_file_accumulates_multiple_drops(self, spill_file):
        c = TelemetryCollector(max_buffer=1, disk_spill_path=spill_file)
        spilled_events = []
        spilled_events.append(c.collect("battery_status", **_battery_data()))
        for i in range(4):
            ev = c.collect("battery_status", voltage_mv=6000 + i, percentage=float(i))
            if i < 3:
                spilled_events.append(ev)

        with open(spill_file, encoding="utf-8") as fh:
            lines = [l.strip() for l in fh if l.strip()]

        assert len(lines) == 4
        for line in lines:
            data = json.loads(line)
            assert "event_id" in data

    def test_no_spill_without_path(self, tmp_path):
        c = TelemetryCollector(max_buffer=1, disk_spill_path=None)
        c.collect("battery_status", **_battery_data())
        c.collect("battery_status", **_battery_data())  # triggers drop, no spill
        assert c.dropped_count == 1

    def test_spill_directory_auto_created(self, tmp_path):
        nested_path = str(tmp_path / "deep" / "nested" / "spill.jsonl")
        c = TelemetryCollector(max_buffer=1, disk_spill_path=nested_path)
        c.collect("battery_status", **_battery_data())
        c.collect("battery_status", **_battery_data())

        assert os.path.exists(nested_path)

    def test_spill_oserror_does_not_raise(self, tmp_path):
        bad_path = "/proc/nonexistent_kernel_path/telemetry.jsonl"
        c = TelemetryCollector(max_buffer=1, disk_spill_path=bad_path)
        c.collect("battery_status", **_battery_data())
        # Should not raise even with a bad path
        c.collect("battery_status", **_battery_data())
        assert c.dropped_count == 1


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_collect_does_not_lose_events(self):
        c = TelemetryCollector(max_buffer=1000)
        errors: list = []

        def worker():
            try:
                for _ in range(50):
                    c.collect("battery_status", **_battery_data())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        assert c.size() == 500  # max_buffer caps at 1000 but 10*50=500

    def test_concurrent_flush_and_collect(self):
        c = TelemetryCollector(max_buffer=500)
        errors: list = []
        all_flushed: list = []
        lock = threading.Lock()

        def producer():
            try:
                for _ in range(100):
                    c.collect("battery_status", **_battery_data())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def consumer():
            try:
                for _ in range(10):
                    events = c.flush()
                    with lock:
                        all_flushed.extend(events)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=producer) for _ in range(5)]
        threads += [threading.Thread(target=consumer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_drops_accumulate_dropped_count(self):
        c = TelemetryCollector(max_buffer=10)
        errors: list = []

        def worker():
            try:
                for _ in range(50):
                    c.collect("battery_status", **_battery_data())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert c.size() == 10
        total = c.size() + c.dropped_count
        assert total == 250  # 5 threads × 50 events


# ---------------------------------------------------------------------------
# Payload is JSON-serialisable
# ---------------------------------------------------------------------------


class TestJsonSerializable:
    def test_collected_event_is_json_serialisable(self, collector):
        event = collector.collect("battery_status", **_battery_data())
        serialized = json.dumps(event)
        parsed = json.loads(serialized)
        assert parsed["event_type"] == "battery_status"

    def test_all_events_in_buffer_are_json_serialisable(self, collector):
        collector.collect("battery_status", **_battery_data())
        collector.collect("command_received", **_command_received_data())
        collector.collect("command_executed", **_command_executed_data())
        for event in collector.get_events():
            json.dumps(event)  # Should not raise


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_max_buffer_one(self):
        c = TelemetryCollector(max_buffer=1)
        e1 = c.collect("battery_status", **_battery_data())
        e2 = c.collect("battery_status", voltage_mv=6000, percentage=30.0)
        assert c.size() == 1
        events = c.get_events()
        assert events[0]["event_id"] == e2["event_id"]
        assert c.dropped_count == 1

    def test_empty_payload_kwargs(self):
        c = TelemetryCollector(validate=False)
        event = c.collect("motor_status")
        assert event is not None
        assert event["payload"] == {}

    def test_payload_with_nested_dict(self):
        c = TelemetryCollector(validate=False)
        event = c.collect("motor_status", nested={"a": 1, "b": [2, 3]})
        assert event["payload"]["nested"] == {"a": 1, "b": [2, 3]}

    def test_collect_command_executed_with_optional_fields(self, collector):
        event = collector.collect(
            "command_executed",
            command="forward",
            success=False,
            duration_ms=120.5,
            controller_type="ps4",
        )
        assert event is not None
        assert event["payload"]["success"] is False
        assert event["payload"]["duration_ms"] == 120.5

    def test_collect_error_event(self, collector):
        event = collector.collect(
            "error",
            error_type="motor_stall",
            message="Left motor stopped responding",
        )
        assert event is not None
        assert event["payload"]["error_type"] == "motor_stall"

    def test_get_events_returns_list_copy(self, collector):
        collector.collect("battery_status", **_battery_data())
        events = collector.get_events()
        events.append({"fake": True})
        # Original buffer should be unaffected
        assert collector.size() == 1

    def test_validate_flag_false_bypasses_invalid_source(self):
        c = TelemetryCollector(source="invalid_source", validate=False)
        event = c.collect("battery_status", voltage_mv=7200, percentage=80.0)
        assert event is not None
        assert event["source"] == "invalid_source"

    def test_session_id_none_not_in_envelope(self, collector):
        event = collector.collect("battery_status", **_battery_data())
        assert "session_id" not in event

    def test_device_id_none_not_in_envelope(self, collector):
        event = collector.collect("battery_status", **_battery_data())
        assert "device_id" not in event
