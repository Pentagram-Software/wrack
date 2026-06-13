"""
Tests for EventHandler telemetry integration (PEN-123).

Verifies that:
- set_telemetry_collector() attaches/detaches a collector.
- trigger() forwards events to the collector when set.
- event_filter restricts which events are forwarded.
- Existing event-handler behaviour is not affected.
- Collector exceptions do not propagate to callers.
"""

import pytest

from event_handler import EventHandler
from telemetry.collector import TelemetryCollector


# ---------------------------------------------------------------------------
# Backward-compatibility tests (existing behaviour must still pass)
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_trigger_without_collector_does_not_raise(self):
        eh = EventHandler()
        eh.on("click", lambda s: None)
        eh.trigger("click")  # must not raise

    def test_trigger_callbacks_still_fire_with_collector(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        fired = []
        eh.on("move", lambda s: fired.append("move"))
        eh.trigger("move")
        assert fired == ["move"]

    def test_existing_callbacks_fire_before_telemetry(self):
        order = []
        eh = EventHandler()

        class OrderRecordingCollector:
            def collect(self, *args, **kwargs):
                order.append("telemetry")

        eh.on("ping", lambda s: order.append("callback"))
        eh.set_telemetry_collector(OrderRecordingCollector())
        eh.trigger("ping")
        assert order[0] == "callback"
        assert order[1] == "telemetry"

    def test_no_collector_attached_by_default(self):
        eh = EventHandler()
        assert eh._telemetry_collector is None


# ---------------------------------------------------------------------------
# set_telemetry_collector()
# ---------------------------------------------------------------------------


class TestSetTelemetryCollector:
    def test_attach_collector(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        assert eh._telemetry_collector is c

    def test_detach_collector_by_passing_none(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.set_telemetry_collector(None)
        assert eh._telemetry_collector is None

    def test_replace_collector(self):
        eh = EventHandler()
        c1 = TelemetryCollector()
        c2 = TelemetryCollector()
        eh.set_telemetry_collector(c1)
        eh.set_telemetry_collector(c2)
        assert eh._telemetry_collector is c2

    def test_filter_stored_as_set(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c, event_filter=["forward", "turn"])
        assert eh._telemetry_filter == {"forward", "turn"}

    def test_no_filter_stored_as_none(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        assert eh._telemetry_filter is None


# ---------------------------------------------------------------------------
# Event forwarding to collector
# ---------------------------------------------------------------------------


class TestEventForwarding:
    def test_trigger_forwards_event_to_collector(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("forward")
        assert c.buffer_size == 1

    def test_forwarded_event_type_is_command_received(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("drive")
        event = c.peek()[0]
        assert event["event_type"] == "command_received"

    def test_forwarded_event_payload_contains_command(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("drive")
        event = c.peek()[0]
        assert event["payload"]["command"] == "drive"

    def test_multiple_triggers_produce_multiple_events(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("forward")
        eh.trigger("turn")
        eh.trigger("stop")
        assert c.buffer_size == 3

    def test_no_forwarding_after_collector_detached(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("forward")
        eh.set_telemetry_collector(None)
        eh.trigger("stop")
        assert c.buffer_size == 1


# ---------------------------------------------------------------------------
# Event filtering
# ---------------------------------------------------------------------------


class TestEventFiltering:
    def test_only_filtered_events_are_collected(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c, event_filter=["forward", "reverse"])
        eh.trigger("forward")
        eh.trigger("turn")
        eh.trigger("reverse")
        eh.trigger("stop")
        assert c.buffer_size == 2
        commands = {e["payload"]["command"] for e in c.peek()}
        assert commands == {"forward", "reverse"}

    def test_no_filter_collects_all_events(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        for name in ["a", "b", "c", "d"]:
            eh.trigger(name)
        assert c.buffer_size == 4

    def test_empty_filter_collects_nothing(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c, event_filter=[])
        eh.trigger("forward")
        eh.trigger("stop")
        assert c.buffer_size == 0


# ---------------------------------------------------------------------------
# Collector exceptions do not propagate
# ---------------------------------------------------------------------------


class TestCollectorExceptionIsolation:
    def test_collector_error_does_not_raise_to_caller(self):
        class BrokenCollector:
            def collect(self, *args, **kwargs):
                raise RuntimeError("collector exploded")

        eh = EventHandler()
        eh.set_telemetry_collector(BrokenCollector())
        # Must not raise even though the collector raises
        eh.trigger("forward")  # should silently swallow the error

    def test_callbacks_still_fire_when_collector_raises(self):
        class BrokenCollector:
            def collect(self, *args, **kwargs):
                raise RuntimeError("broken")

        fired = []
        eh = EventHandler()
        eh.set_telemetry_collector(BrokenCollector())
        eh.on("move", lambda s: fired.append(True))
        eh.trigger("move")
        assert fired == [True]
