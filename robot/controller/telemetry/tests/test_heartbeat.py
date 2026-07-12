"""
Tests for telemetry.heartbeat.HeartbeatSender (PEN-229).

Acceptance criteria verified here:
- EV3 sends a type=health payload to the unified ingress on a fixed interval.
- Payload includes at minimum a liveness/alive signal (device_status,
  status="connected", tagged type="health").
- Unit tests cover the sender logic (timing, lifecycle, crash containment,
  MicroPython Thread() constraints).
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from telemetry.collector import TelemetryCollector
from telemetry.heartbeat import HeartbeatSender, DEFAULT_HEARTBEAT_INTERVAL


def _make_sender():
    """Build a mock TelemetrySender-like object."""
    sender = MagicMock()
    sender.send_events_async = MagicMock()
    return sender


# ---------------------------------------------------------------------------
# Default interval / construction
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_default_interval_constant(self):
        assert DEFAULT_HEARTBEAT_INTERVAL == 30

    def test_heartbeat_sender_uses_default_interval(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        assert hb.interval == DEFAULT_HEARTBEAT_INTERVAL


class TestConfiguration:
    def test_custom_interval(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s, interval=5)
        assert hb.interval == 5

    def test_zero_interval_rejected(self):
        c = TelemetryCollector()
        s = _make_sender()
        with pytest.raises(ValueError):
            HeartbeatSender(c, s, interval=0)

    def test_negative_interval_rejected(self):
        c = TelemetryCollector()
        s = _make_sender()
        with pytest.raises(ValueError):
            HeartbeatSender(c, s, interval=-1)

    def test_not_running_by_default(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        assert not hb.is_running


# ---------------------------------------------------------------------------
# send_now — manual/immediate send
# ---------------------------------------------------------------------------


class TestSendNow:
    def test_returns_event(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        event = hb.send_now()
        assert event is not None
        assert event["event_type"] == "device_status"
        assert event["type"] == "health"

    def test_does_not_buffer_into_collector(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        hb.send_now()
        assert c.buffer_size == 0

    def test_sends_via_sender_async(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        event = hb.send_now()
        s.send_events_async.assert_called_once_with([event])

    def test_payload_is_liveness_signal(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        event = hb.send_now()
        assert event["payload"]["status"] == "connected"


# ---------------------------------------------------------------------------
# Start / stop lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_start_sets_running_true(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        hb.start()
        assert hb.is_running
        hb.stop()

    def test_start_does_not_use_daemon_or_name_kwargs(self):
        """Regression (PEN-188): Thread() must omit daemon/name kwargs.

        Pybricks MicroPython's threading.Thread accepts only ``target`` —
        passing ``daemon`` or ``name`` raises TypeError and crashes the app
        on the EV3.
        """
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)

        original_thread = threading.Thread
        created_kwargs = []

        def capturing_thread(*args, **kwargs):
            created_kwargs.append(kwargs)
            return original_thread(*args, **kwargs)

        with patch(
            "telemetry.heartbeat._threading.Thread",
            side_effect=capturing_thread,
        ):
            hb.start()
        hb.stop()

        assert len(created_kwargs) == 1, "Expected exactly one Thread to be created"
        assert "daemon" not in created_kwargs[0]
        assert "name" not in created_kwargs[0]

    def test_stop_sets_running_false(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        hb.start()
        hb.stop()
        assert not hb.is_running

    def test_double_start_is_safe(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        hb.start()
        hb.start()  # second call must not raise
        assert hb.is_running
        hb.stop()

    def test_stop_before_start_is_safe(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        hb.stop()  # must not raise

    def test_start_sends_at_least_one_heartbeat(self):
        """The loop fires immediately on the first tick, so a real (short)
        start/stop cycle should have already sent at least one heartbeat."""
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s, interval=1)
        hb.start()
        hb._thread.join(timeout=2.0)  # loop ticks every 1s; give it time to fire once
        hb.stop()
        assert s.send_events_async.call_count >= 1


# ---------------------------------------------------------------------------
# Timing — periodic send via mocked time (fake-clock harness, mirrors
# StatusCollector's TestCollectionTiming)
# ---------------------------------------------------------------------------


class TestSendTiming:
    def _run_fake_loop(self, hb: HeartbeatSender, tick_seconds: float, ticks: int):
        """Execute the send logic for *ticks* iterations using a fake clock,
        mirroring HeartbeatSender._run without blocking on real time.sleep."""
        fake_time = [0.0]
        last = [-hb.interval]

        for _ in range(ticks):
            now = fake_time[0]
            if now - last[0] >= hb.interval:
                hb._send_heartbeat()
                last[0] = now
            fake_time[0] += tick_seconds

    def test_heartbeat_sent_at_correct_interval(self):
        """With interval=30 and 1-second ticks, expect exactly 4 sends over
        120 ticks (t=0,30,60,90)."""
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s, interval=30)

        self._run_fake_loop(hb, tick_seconds=1, ticks=120)

        assert s.send_events_async.call_count == 4

    def test_custom_interval_changes_send_frequency(self):
        """Custom interval=5 should produce 6 sends in 30 ticks (t=0,5,...,25)."""
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s, interval=5)

        self._run_fake_loop(hb, tick_seconds=1, ticks=30)

        assert s.send_events_async.call_count == 6


# ---------------------------------------------------------------------------
# Crash containment — a bad build/send must never kill the loop
# ---------------------------------------------------------------------------


class TestCrashContainment:
    def test_collector_build_failure_does_not_raise(self):
        c = TelemetryCollector()
        c.create_heartbeat_event = MagicMock(side_effect=RuntimeError("boom"))
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        assert hb._send_heartbeat() is None
        s.send_events_async.assert_not_called()

    def test_sender_send_failure_does_not_raise(self):
        c = TelemetryCollector()
        s = _make_sender()
        s.send_events_async = MagicMock(side_effect=RuntimeError("network down"))
        hb = HeartbeatSender(c, s)
        event = hb._send_heartbeat()  # must not raise
        assert event is not None

    def test_periodic_loop_survives_persistent_send_failure(self):
        """Even if every send attempt fails, subsequent ticks must still be
        attempted — the loop itself must never die."""
        c = TelemetryCollector()
        s = _make_sender()
        s.send_events_async = MagicMock(side_effect=RuntimeError("boom"))
        hb = HeartbeatSender(c, s, interval=10)

        TestSendTiming()._run_fake_loop(hb, tick_seconds=1, ticks=30)
        assert s.send_events_async.call_count == 3  # t=0, 10, 20
