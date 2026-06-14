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
from unittest.mock import MagicMock, call

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


# ---------------------------------------------------------------------------
# Exact collect() call-argument verification (MagicMock isolation tests)
# ---------------------------------------------------------------------------


class TestCollectCallArguments:
    """Isolation tests using MagicMock to verify the exact arguments forwarded
    to ``collector.collect()`` on each ``trigger()`` call."""

    @pytest.mark.parametrize("event_name", ["forward", "reverse", "turn", "stop", "drive"])
    def test_collect_called_with_command_received_event_type(self, event_name):
        eh = EventHandler()
        mock_collector = MagicMock()
        eh.set_telemetry_collector(mock_collector)
        eh.trigger(event_name)
        mock_collector.collect.assert_called_once_with(
            "command_received",
            command=event_name,
            controller_type="unknown",
        )

    @pytest.mark.parametrize("event_name", ["forward", "stop", "left_joystick"])
    def test_collect_receives_controller_type_unknown(self, event_name):
        eh = EventHandler()
        mock_collector = MagicMock()
        eh.set_telemetry_collector(mock_collector)
        eh.trigger(event_name)
        _, kwargs = mock_collector.collect.call_args
        assert kwargs.get("controller_type") == "unknown"

    @pytest.mark.parametrize("event_name", ["forward", "stop", "left_joystick"])
    def test_collect_receives_correct_command_kwarg(self, event_name):
        eh = EventHandler()
        mock_collector = MagicMock()
        eh.set_telemetry_collector(mock_collector)
        eh.trigger(event_name)
        _, kwargs = mock_collector.collect.call_args
        assert kwargs.get("command") == event_name

    def test_collect_not_called_without_collector(self):
        """No collector → collect() must never be invoked; callbacks still fire."""
        eh = EventHandler()
        fired = []
        eh.on("click", lambda s: fired.append(True))
        eh.trigger("click")
        assert fired == [True]

    def test_collect_not_called_after_detach(self):
        eh = EventHandler()
        mock_collector = MagicMock()
        eh.set_telemetry_collector(mock_collector)
        eh.set_telemetry_collector(None)
        eh.trigger("forward")
        mock_collector.collect.assert_not_called()

    @pytest.mark.parametrize("non_filtered_event", ["fire", "scan", "spin"])
    def test_collect_not_called_for_non_filtered_events(self, non_filtered_event):
        eh = EventHandler()
        mock_collector = MagicMock()
        eh.set_telemetry_collector(mock_collector, event_filter=["drive", "stop"])
        eh.trigger(non_filtered_event)
        mock_collector.collect.assert_not_called()


# ---------------------------------------------------------------------------
# Multiple callbacks + telemetry interaction
# ---------------------------------------------------------------------------


class TestMultipleCallbacks:
    """Verifies that multiple registered callbacks all fire and that telemetry
    is emitted exactly once per ``trigger()`` call regardless of how many
    callbacks are registered."""

    def test_all_multiple_callbacks_fire_with_collector(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        fired = []
        eh.on("go", lambda s: fired.append("cb1"))
        eh.on("go", lambda s: fired.append("cb2"))
        eh.on("go", lambda s: fired.append("cb3"))
        eh.trigger("go")
        assert fired == ["cb1", "cb2", "cb3"]

    def test_telemetry_called_once_per_trigger_with_multiple_callbacks(self):
        eh = EventHandler()
        mock_collector = MagicMock()
        eh.set_telemetry_collector(mock_collector)
        eh.on("go", lambda s: None)
        eh.on("go", lambda s: None)
        eh.on("go", lambda s: None)
        eh.trigger("go")
        mock_collector.collect.assert_called_once()

    def test_all_callbacks_execute_before_single_telemetry_call(self):
        """Ordering guarantee: all callbacks precede the single telemetry call."""
        order = []
        eh = EventHandler()
        mock_collector = MagicMock()
        mock_collector.collect.side_effect = lambda *a, **kw: order.append("telemetry")
        eh.on("go", lambda s: order.append("cb1"))
        eh.on("go", lambda s: order.append("cb2"))
        eh.on("go", lambda s: order.append("cb3"))
        eh.set_telemetry_collector(mock_collector)
        eh.trigger("go")
        assert order == ["cb1", "cb2", "cb3", "telemetry"]

    def test_multiple_triggers_each_produce_one_telemetry_event(self):
        """N trigger calls → exactly N collect() calls."""
        eh = EventHandler()
        mock_collector = MagicMock()
        eh.set_telemetry_collector(mock_collector)
        eh.on("go", lambda s: None)
        eh.on("go", lambda s: None)
        for _ in range(5):
            eh.trigger("go")
        assert mock_collector.collect.call_count == 5
