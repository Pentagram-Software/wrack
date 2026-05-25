"""Unit tests for telemetry.collector.TelemetryCollector."""

import re
import threading
import uuid
from datetime import datetime, timezone

import pytest

from telemetry.collector import TelemetryCollector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def _assert_valid_envelope(event: dict) -> None:
    assert _UUID_RE.match(event["event_id"]), "event_id must be a UUID"
    assert event["source"] == "ev3"
    assert _ISO_RE.match(event["timestamp"]), "timestamp must be ISO-8601 UTC"
    assert isinstance(event["payload"], dict)
    assert isinstance(event["session_id"], str)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_session_id_is_uuid(self):
        c = TelemetryCollector()
        assert _UUID_RE.match(c.session_id)

    def test_custom_session_id_preserved(self):
        sid = str(uuid.uuid4())
        c = TelemetryCollector(session_id=sid)
        assert c.session_id == sid

    def test_default_device_id_is_none(self):
        c = TelemetryCollector()
        assert c.device_id is None

    def test_custom_device_id_preserved(self):
        c = TelemetryCollector(device_id="ev3-42")
        assert c.device_id == "ev3-42"

    def test_default_buffer_is_empty(self):
        c = TelemetryCollector()
        assert c.size() == 0

    def test_default_max_buffer_size(self):
        c = TelemetryCollector()
        assert c.max_buffer_size == 500


# ---------------------------------------------------------------------------
# collect()
# ---------------------------------------------------------------------------


class TestCollect:
    def test_collect_returns_event_dict(self):
        c = TelemetryCollector()
        event = c.collect("battery_status", voltage_mv=7200, percentage=85)
        assert isinstance(event, dict)

    def test_collect_fills_envelope(self):
        c = TelemetryCollector()
        event = c.collect("battery_status", voltage_mv=7200, percentage=85)
        _assert_valid_envelope(event)

    def test_collect_event_type_set_correctly(self):
        c = TelemetryCollector()
        event = c.collect("motor_status", motors={})
        assert event["event_type"] == "motor_status"

    def test_collect_payload_contains_kwargs(self):
        c = TelemetryCollector()
        event = c.collect("battery_status", voltage_mv=7200, percentage=85)
        assert event["payload"]["voltage_mv"] == 7200
        assert event["payload"]["percentage"] == 85

    def test_collect_includes_device_id_when_set(self):
        c = TelemetryCollector(device_id="ev3-001")
        event = c.collect("error", error_type="test", message="boom")
        assert event["device_id"] == "ev3-001"

    def test_collect_omits_device_id_key_when_none(self):
        c = TelemetryCollector()
        event = c.collect("battery_status", voltage_mv=7200, percentage=85)
        assert "device_id" not in event

    def test_collect_increments_size(self):
        c = TelemetryCollector()
        c.collect("battery_status", voltage_mv=7200, percentage=85)
        c.collect("battery_status", voltage_mv=7100, percentage=80)
        assert c.size() == 2

    def test_collect_session_id_consistent_across_events(self):
        c = TelemetryCollector()
        e1 = c.collect("battery_status", voltage_mv=7200, percentage=85)
        e2 = c.collect("battery_status", voltage_mv=7100, percentage=80)
        assert e1["session_id"] == e2["session_id"] == c.session_id

    def test_each_event_has_unique_event_id(self):
        c = TelemetryCollector()
        ids = {c.collect("motor_status", motors={})["event_id"] for _ in range(10)}
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# Buffer overflow (FIFO drop)
# ---------------------------------------------------------------------------


class TestBufferOverflow:
    def test_buffer_does_not_exceed_max_size(self):
        c = TelemetryCollector(max_buffer_size=5)
        for i in range(10):
            c.collect("battery_status", voltage_mv=7200, percentage=i)
        assert c.size() == 5

    def test_oldest_event_dropped_on_overflow(self):
        c = TelemetryCollector(max_buffer_size=3)
        for i in range(5):
            c.collect("battery_status", voltage_mv=7200, percentage=i)
        events = c.peek()
        percentages = [e["payload"]["percentage"] for e in events]
        # Events 0,1 dropped; events 2,3,4 remain
        assert percentages == [2, 3, 4]


# ---------------------------------------------------------------------------
# flush() / peek() / clear()
# ---------------------------------------------------------------------------


class TestFlushPeekClear:
    def test_flush_returns_all_events(self):
        c = TelemetryCollector()
        c.collect("battery_status", voltage_mv=7200, percentage=85)
        c.collect("motor_status", motors={})
        events = c.flush()
        assert len(events) == 2

    def test_flush_clears_buffer(self):
        c = TelemetryCollector()
        c.collect("battery_status", voltage_mv=7200, percentage=85)
        c.flush()
        assert c.size() == 0

    def test_flush_empty_returns_empty_list(self):
        c = TelemetryCollector()
        assert c.flush() == []

    def test_peek_does_not_clear_buffer(self):
        c = TelemetryCollector()
        c.collect("battery_status", voltage_mv=7200, percentage=85)
        c.peek()
        assert c.size() == 1

    def test_peek_returns_copy(self):
        c = TelemetryCollector()
        c.collect("battery_status", voltage_mv=7200, percentage=85)
        snapshot = c.peek()
        snapshot.clear()
        assert c.size() == 1

    def test_clear_empties_buffer(self):
        c = TelemetryCollector()
        for _ in range(5):
            c.collect("motor_status", motors={})
        c.clear()
        assert c.size() == 0


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_collects_do_not_corrupt_buffer(self):
        c = TelemetryCollector(max_buffer_size=10_000)
        errors = []

        def worker():
            try:
                for _ in range(500):
                    c.collect("battery_status", voltage_mv=7200, percentage=85)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert c.size() <= 10_000

    def test_flush_while_collecting_is_safe(self):
        c = TelemetryCollector(max_buffer_size=10_000)
        flushed_total = []
        stop_flag = threading.Event()

        def collector_worker():
            for _ in range(200):
                c.collect("motor_status", motors={})

        def flusher_worker():
            while not stop_flag.is_set():
                flushed_total.extend(c.flush())

        threads = [threading.Thread(target=collector_worker) for _ in range(5)]
        flusher = threading.Thread(target=flusher_worker)
        flusher.start()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        stop_flag.set()
        flusher.join()

        # Drain any remainder
        flushed_total.extend(c.flush())
        assert len(flushed_total) == 1000
