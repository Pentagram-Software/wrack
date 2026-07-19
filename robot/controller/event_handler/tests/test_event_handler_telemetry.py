"""
Tests for EventHandler telemetry integration (PEN-123 / PEN-165).

Verifies that:
- set_telemetry_collector() attaches/detaches a collector.
- trigger() emits command_received (before callbacks) and command_executed (after).
- controller_type is propagated from _controller_type attribute.
- event_filter restricts which events are forwarded.
- Existing event-handler behaviour is not affected.
- Collector exceptions do not propagate to callers.
- command_executed carries timing and success/failure information.
"""

import pytest
from unittest.mock import MagicMock

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

    def test_command_received_emitted_before_callbacks_command_executed_after(self):
        """New ordering: command_received → callback → command_executed."""
        order = []
        eh = EventHandler()

        class OrderRecordingCollector:
            def collect_command_received(self, *args, **kwargs):
                order.append("command_received")

            def collect_command_executed(self, *args, **kwargs):
                order.append("command_executed")

        eh.on("ping", lambda s: order.append("callback"))
        eh.set_telemetry_collector(OrderRecordingCollector())
        eh.trigger("ping")
        assert order == ["command_received", "callback", "command_executed"]

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

    def test_excluded_events_stored_as_set(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c, excluded_events=["left_joystick"])
        assert eh._telemetry_excluded_events == {"left_joystick"}


# ---------------------------------------------------------------------------
# Event forwarding to collector
# ---------------------------------------------------------------------------


class TestEventForwarding:
    def test_trigger_produces_command_received_and_command_executed(self):
        """One trigger() call produces two buffered events."""
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("forward")
        assert c.buffer_size == 2

    def test_forwarded_event_type_is_command_received(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("drive")
        events = c.peek()
        types = [e["event_type"] for e in events]
        assert "command_received" in types

    def test_forwarded_event_payload_contains_command(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("drive")
        received = next(e for e in c.peek() if e["event_type"] == "command_received")
        assert received["payload"]["command"] == "drive"

    def test_multiple_triggers_produce_two_events_each(self):
        """3 triggers → 6 events (command_received + command_executed per trigger)."""
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("forward")
        eh.trigger("turn")
        eh.trigger("stop")
        assert c.buffer_size == 6

    def test_no_forwarding_after_collector_detached(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("forward")
        eh.set_telemetry_collector(None)
        eh.trigger("stop")
        # Only 2 events from the first trigger; none from the second
        assert c.buffer_size == 2


# ---------------------------------------------------------------------------
# Event filtering
# ---------------------------------------------------------------------------


class TestEventFiltering:
    def test_only_filtered_events_are_collected(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c, event_filter=["forward", "reverse"])
        eh.trigger("forward")
        eh.trigger("turn")    # filtered out
        eh.trigger("reverse")
        eh.trigger("stop")    # filtered out
        # 2 matching triggers × 2 events each
        assert c.buffer_size == 4
        commands = {e["payload"]["command"] for e in c.peek()}
        assert commands == {"forward", "reverse"}

    def test_no_filter_collects_all_events(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        for name in ["a", "b", "c", "d"]:
            eh.trigger(name)
        # 4 triggers × 2 events each
        assert c.buffer_size == 8

    def test_empty_filter_collects_nothing(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c, event_filter=[])
        eh.trigger("forward")
        eh.trigger("stop")
        assert c.buffer_size == 0

    def test_excluded_event_is_not_collected_but_other_events_are(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c, excluded_events=["left_joystick"])
        eh.trigger("left_joystick")
        eh.trigger("cross_button")
        assert c.buffer_size == 2
        assert {e["payload"]["command"] for e in c.peek()} == {"cross_button"}


# ---------------------------------------------------------------------------
# Collector exceptions do not propagate
# ---------------------------------------------------------------------------


class TestCollectorExceptionIsolation:
    def test_collector_error_does_not_raise_to_caller(self):
        class BrokenCollector:
            def collect_command_received(self, *args, **kwargs):
                raise RuntimeError("collector exploded")

            def collect_command_executed(self, *args, **kwargs):
                raise RuntimeError("collector exploded")

        eh = EventHandler()
        eh.set_telemetry_collector(BrokenCollector())
        # Must not raise even though the collector raises
        eh.trigger("forward")  # should silently swallow the error

    def test_callbacks_still_fire_when_collector_raises(self):
        class BrokenCollector:
            def collect_command_received(self, *args, **kwargs):
                raise RuntimeError("broken")

            def collect_command_executed(self, *args, **kwargs):
                raise RuntimeError("broken")

        fired = []
        eh = EventHandler()
        eh.set_telemetry_collector(BrokenCollector())
        eh.on("move", lambda s: fired.append(True))
        eh.trigger("move")
        assert fired == [True]


# controller_type propagation (PEN-165)
# ---------------------------------------------------------------------------


class TestControllerTypeInEvents:
    def test_default_controller_type_is_unknown(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("move")
        received = next(e for e in c.peek() if e["event_type"] == "command_received")
        assert received["payload"]["controller_type"] == "unknown"

    def test_custom_controller_type_propagated_to_command_received(self):
        class CustomHandler(EventHandler):
            _controller_type = "ps4"

        eh = CustomHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("move")
        received = next(e for e in c.peek() if e["event_type"] == "command_received")
        assert received["payload"]["controller_type"] == "ps4"

    def test_custom_controller_type_propagated_to_command_executed(self):
        class CustomHandler(EventHandler):
            _controller_type = "network_remote"

        eh = CustomHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("move")
        executed = next(e for e in c.peek() if e["event_type"] == "command_executed")
        assert executed["payload"]["controller_type"] == "network_remote"


# ---------------------------------------------------------------------------
# command_executed event details (PEN-165)
# ---------------------------------------------------------------------------


class TestCommandExecutedEvent:
    def test_command_executed_emitted_on_every_trigger(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("move")
        executed = [e for e in c.peek() if e["event_type"] == "command_executed"]
        assert len(executed) == 1

    def test_command_executed_success_true_when_no_exception(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.on("move", lambda s: None)
        eh.trigger("move")
        executed = next(e for e in c.peek() if e["event_type"] == "command_executed")
        assert executed["payload"]["success"] is True

    def test_command_executed_success_false_when_callback_raises(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.on("move", lambda s: (_ for _ in ()).throw(ValueError("boom")))

        with pytest.raises(ValueError):
            eh.trigger("move")

        executed = next(e for e in c.peek() if e["event_type"] == "command_executed")
        assert executed["payload"]["success"] is False

    def test_command_executed_error_message_set_when_callback_raises(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.on("move", lambda s: (_ for _ in ()).throw(ValueError("boom")))

        with pytest.raises(ValueError):
            eh.trigger("move")

        executed = next(e for e in c.peek() if e["event_type"] == "command_executed")
        assert "boom" in executed["payload"]["error_message"]

    def test_command_executed_duration_ms_is_non_negative(self):
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("move")
        executed = next(e for e in c.peek() if e["event_type"] == "command_executed")
        duration = executed["payload"].get("duration_ms")
        assert duration is not None
        assert duration >= 0

    def test_command_executed_emitted_even_when_callback_raises(self):
        """command_executed must be emitted before the exception propagates."""
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.on("move", lambda s: (_ for _ in ()).throw(RuntimeError("err")))

        with pytest.raises(RuntimeError):
            eh.trigger("move")

        # Both command_received and command_executed should be in the buffer
        types = {e["event_type"] for e in c.peek()}
        assert "command_received" in types
        assert "command_executed" in types

    def test_exception_from_callback_propagates_after_telemetry(self):
        """The original exception from a callback must still propagate."""
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.on("move", lambda s: (_ for _ in ()).throw(RuntimeError("propagate_me")))

        with pytest.raises(RuntimeError, match="propagate_me"):
            eh.trigger("move")

    def test_command_executed_respects_event_filter(self):
        """command_executed is not emitted for filtered-out events."""
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c, event_filter=["allowed"])
        eh.trigger("allowed")
        eh.trigger("blocked")
        executed = [e for e in c.peek() if e["event_type"] == "command_executed"]
        assert len(executed) == 1
        assert executed[0]["payload"]["command"] == "allowed"

    def test_command_executed_payload_passes_schema_validation(self):
        """command_executed event passes schema validation."""
        from telemetry.schemas import validate_event
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.on("move", lambda s: None)
        eh.trigger("move")
        executed = next(e for e in c.peek() if e["event_type"] == "command_executed")
        validate_event(executed)  # must not raise

    def test_command_received_payload_passes_schema_validation(self):
        """command_received event passes schema validation."""
        from telemetry.schemas import validate_event
        eh = EventHandler()
        c = TelemetryCollector()
        eh.set_telemetry_collector(c)
        eh.trigger("move")
        received = next(e for e in c.peek() if e["event_type"] == "command_received")
        validate_event(received)  # must not raise
