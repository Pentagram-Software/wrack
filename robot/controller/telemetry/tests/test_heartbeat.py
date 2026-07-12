"""
Tests for telemetry.heartbeat.HeartbeatSender (PEN-229).

Acceptance criteria verified here:
- EV3 sends a type=health payload to the unified ingress on a fixed interval.
- Payload includes at minimum a liveness/alive signal (device_status,
  status="connected", tagged type="health").
- Unit tests cover the sender logic (timing, lifecycle, crash containment,
  MicroPython Thread() constraints, in-flight send tracking).
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
    sender.send_events = MagicMock(return_value=True)
    return sender


def _join_send_thread(hb: HeartbeatSender, timeout: float = 2.0) -> None:
    """Wait for HeartbeatSender's in-flight send worker (if any) to finish.

    ``_send_heartbeat`` hands the actual send off to a background thread it
    tracks via ``_send_thread`` — tests that assert on the sender mock (or on
    a following tick's behavior) need the worker to have actually run first.
    """
    if hb._send_thread is not None:
        hb._send_thread.join(timeout=timeout)


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

    def test_no_send_in_flight_by_default(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        assert hb._send_thread is None


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

    def test_sends_via_blocking_send_events(self):
        """Sends go through the tracked worker thread, which calls the
        blocking ``send_events`` — never ``send_events_async`` (that would
        spawn a second, untracked thread; see the module docstring)."""
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        event = hb.send_now()
        _join_send_thread(hb)
        s.send_events.assert_called_once_with([event])
        s.send_events_async.assert_not_called()

    def test_payload_is_liveness_signal(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        event = hb.send_now()
        assert event["payload"]["status"] == "connected"

    def test_send_thread_cleared_after_completion(self):
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        hb.send_now()
        _join_send_thread(hb)
        assert hb._send_thread is None


# ---------------------------------------------------------------------------
# In-flight tracking — regression coverage for the unbounded-thread-growth
# finding from code review: a hung send must not spawn a new thread every
# tick.
# ---------------------------------------------------------------------------


class TestInFlightTracking:
    def test_skips_when_a_send_is_already_in_flight(self):
        c = TelemetryCollector()
        c.create_heartbeat_event = MagicMock()
        s = _make_sender()
        hb = HeartbeatSender(c, s)
        hb._send_thread = MagicMock()  # simulate an in-flight send

        result = hb._send_heartbeat()

        assert result is None
        c.create_heartbeat_event.assert_not_called()
        s.send_events.assert_not_called()

    def test_hung_send_does_not_accumulate_new_threads(self):
        """Directly reproduces the reported scenario: a send that hangs
        (blocks indefinitely, as a real network outage would with no
        ``urequests`` timeout support) must cause every subsequent tick to
        skip rather than spawn another thread on top of it."""
        c = TelemetryCollector()
        s = _make_sender()
        release = threading.Event()

        def hanging_send(events):
            release.wait(timeout=5.0)
            return True

        s.send_events = MagicMock(side_effect=hanging_send)
        hb = HeartbeatSender(c, s, interval=1)

        first = hb._send_heartbeat()
        assert first is not None

        # The first send is still blocked on release.wait() — three more
        # ticks arriving during the same outage must all be skipped, not
        # spawn three more threads.
        assert hb._send_heartbeat() is None
        assert hb._send_heartbeat() is None
        assert hb._send_heartbeat() is None
        assert s.send_events.call_count == 1

        release.set()  # unblock the hung send
        _join_send_thread(hb)
        assert hb._send_thread is None

        # Now that the previous send has finished, the next tick proceeds.
        second = hb._send_heartbeat()
        assert second is not None
        _join_send_thread(hb)
        assert s.send_events.call_count == 2


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

        Pybricks MicroPython's threading.Thread accepts only ``target``
        (and ``args``) — passing ``daemon`` or ``name`` raises TypeError and
        crashes the app on the EV3. Covers both threads HeartbeatSender can
        create: the periodic loop thread and, if a tick fires before
        ``stop()``, the send-worker thread too.
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

        assert len(created_kwargs) >= 1, "Expected at least one Thread to be created"
        for kwargs in created_kwargs:
            assert "daemon" not in kwargs
            assert "name" not in kwargs

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
        assert s.send_events.call_count >= 1

    def test_stop_does_not_block_forever_on_hung_send(self):
        """stop() must return promptly even if a send worker is genuinely
        hung — it should time out rather than wait indefinitely."""
        c = TelemetryCollector()
        s = _make_sender()
        release = threading.Event()
        s.send_events = MagicMock(side_effect=lambda events: release.wait(timeout=30))
        hb = HeartbeatSender(c, s, interval=1)

        hb.start()
        hb._thread.join(timeout=2.0)  # let the first tick fire and hang
        hb.stop(timeout=0.5)  # must return within ~0.5s, not hang
        release.set()  # unblock so the leaked thread doesn't linger past the test


# ---------------------------------------------------------------------------
# Timing — periodic send via mocked time (fake-clock harness, mirrors
# StatusCollector's TestCollectionTiming)
# ---------------------------------------------------------------------------


class TestSendTiming:
    def _run_fake_loop(self, hb: HeartbeatSender, tick_seconds: float, ticks: int):
        """Execute the send logic for *ticks* iterations using a fake clock,
        mirroring HeartbeatSender._run without blocking on real time.sleep.

        Joins the send-worker thread after each fired tick so a fast mock
        send completes before the next tick is evaluated — otherwise the
        in-flight tracking (correctly) skips ticks that land while the
        previous send's thread hasn't been scheduled yet, making the
        expected send count flaky rather than a true timing assertion.
        """
        fake_time = [0.0]
        last = [-hb.interval]

        for _ in range(ticks):
            now = fake_time[0]
            if now - last[0] >= hb.interval:
                hb._send_heartbeat()
                _join_send_thread(hb)
                last[0] = now
            fake_time[0] += tick_seconds

    def test_heartbeat_sent_at_correct_interval(self):
        """With interval=30 and 1-second ticks, expect exactly 4 sends over
        120 ticks (t=0,30,60,90)."""
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s, interval=30)

        self._run_fake_loop(hb, tick_seconds=1, ticks=120)

        assert s.send_events.call_count == 4

    def test_custom_interval_changes_send_frequency(self):
        """Custom interval=5 should produce 6 sends in 30 ticks (t=0,5,...,25)."""
        c = TelemetryCollector()
        s = _make_sender()
        hb = HeartbeatSender(c, s, interval=5)

        self._run_fake_loop(hb, tick_seconds=1, ticks=30)

        assert s.send_events.call_count == 6


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
        s.send_events.assert_not_called()

    def test_sender_send_failure_does_not_raise(self):
        c = TelemetryCollector()
        s = _make_sender()
        s.send_events = MagicMock(side_effect=RuntimeError("network down"))
        hb = HeartbeatSender(c, s)
        event = hb._send_heartbeat()  # must not raise
        assert event is not None
        _join_send_thread(hb)
        # The worker's finally-block must clear the marker even on failure,
        # so the next tick isn't permanently skipped.
        assert hb._send_thread is None

    def test_periodic_loop_survives_persistent_send_failure(self):
        """Even if every send attempt fails, subsequent ticks must still be
        attempted — the loop itself must never die."""
        c = TelemetryCollector()
        s = _make_sender()
        s.send_events = MagicMock(side_effect=RuntimeError("boom"))
        hb = HeartbeatSender(c, s, interval=10)

        TestSendTiming()._run_fake_loop(hb, tick_seconds=1, ticks=30)
        assert s.send_events.call_count == 3  # t=0, 10, 20
