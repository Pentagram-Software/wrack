#!/usr/bin/env python3

"""
Tests for the coalesced stick-to-motor control loop.

The read loop used to call the motor callbacks directly for every stick
event.  Each call cost ~10ms on-device, capping the loop at roughly 96
events/second -- below the burst rate of a moving stick -- so a backlog built
up and the kernel's evdev ring buffer overflowed, discarding input.  The read
loop now only caches axis values; this loop applies the latest ones at a
fixed rate.
"""

import struct

import pytest

from robot_controllers import PS4Controller
from robot_controllers.ps4_controller import DEFAULT_CONTROL_LOOP_HZ


EVENT_FORMAT = 'llHHI'
EV_ABS = 3
LEFT_STICK_X = 0
LEFT_STICK_Y = 1
RIGHT_STICK_X = 3
CROSS_BUTTON = 304
EV_KEY = 1


def _event(ev_type, code, value, tv_sec=1000, tv_usec=0):
    return struct.pack(EVENT_FORMAT, tv_sec, tv_usec, ev_type, code, value)


class _FakeDeviceFile:
    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.closed = False

    def read(self, _size):
        if not self._payloads:
            return b""
        return self._payloads.pop(0)

    def close(self):
        self.closed = True


class _RecordingDiagnostics:
    """Captures the reader-timing calls without the real accumulation."""

    def __init__(self, recorded, lag_ms=None):
        self.recorded = recorded
        self.stalls = []
        self._lag_ms = lag_ms
        self._tick = 0.0

    def now(self):
        self._tick += 0.001
        return self._tick

    def record_event(self, ev_type, code, tv_sec=None, tv_usec=None):
        return self._lag_ms

    def record_reader_timing(self, read_ms=None, proc_ms=None, gap_ms=None,
                             lag_ms=None):
        self.recorded.append({
            "read_ms": read_ms,
            "proc_ms": proc_ms,
            "gap_ms": gap_ms,
            "lag_ms": lag_ms,
        })

    def record_drop_stall(self, stall_ms):
        self.stalls.append(stall_ms)

    def record_coalesced(self, event_name):
        pass

    def record_dispatch(self, event_name, duration_ms, failed=False):
        pass

    def record_axis_rejected(self, value):
        pass

    def record_loop_exit(self, *args, **kwargs):
        pass


@pytest.fixture
def controller():
    return PS4Controller()


@pytest.fixture
def no_control_thread(monkeypatch):
    """Suppress the real control thread so ticks can be driven by hand."""
    monkeypatch.setattr(PS4Controller, "_start_control_loop", lambda self: None)


def _read_events(monkeypatch, controller, payloads):
    device = _FakeDeviceFile(payloads)
    monkeypatch.setattr(
        "robot_controllers.ps4_controller.find_controller_device",
        lambda: "/dev/input/event4",
    )
    monkeypatch.setattr(
        "robot_controllers.ps4_controller.open",
        lambda *a, **k: device,
        raising=False,
    )
    controller.run()
    return device


class TestReadLoopDoesNoMotorWork:

    def test_stick_events_do_not_dispatch_from_the_read_loop(
        self, monkeypatch, controller, no_control_thread
    ):
        dispatched = []
        controller.on("left_joystick", lambda ctrl: dispatched.append("l"))
        controller.on("right_joystick", lambda ctrl: dispatched.append("r"))

        _read_events(
            monkeypatch,
            controller,
            [
                _event(EV_ABS, LEFT_STICK_X, 200),
                _event(EV_ABS, LEFT_STICK_Y, 40),
                _event(EV_ABS, RIGHT_STICK_X, 30),
            ],
        )

        assert dispatched == []

    def test_stick_events_still_update_cached_state(
        self, monkeypatch, controller, no_control_thread
    ):
        _read_events(
            monkeypatch, controller, [_event(EV_ABS, LEFT_STICK_X, 255)]
        )

        assert controller.l_left == 1000

    def test_buttons_still_dispatch_immediately(
        self, monkeypatch, controller, no_control_thread
    ):
        pressed = []
        controller.on("cross_button", lambda ctrl: pressed.append(True))

        _read_events(
            monkeypatch, controller, [_event(EV_KEY, CROSS_BUTTON, 1)]
        )

        assert pressed == [True]


class TestControlTick:

    def test_tick_dispatches_a_dirty_stick(self, controller):
        seen = []
        controller.on("left_joystick", lambda ctrl: seen.append(ctrl.l_left))
        controller.l_left = 500
        controller._mark_stick_dirty("left_joystick")

        assert controller._control_tick() == 1
        assert seen == [500]

    def test_tick_is_a_noop_when_nothing_changed(self, controller):
        seen = []
        controller.on("left_joystick", lambda ctrl: seen.append(ctrl))

        assert controller._control_tick() == 0
        assert seen == []

    def test_repeated_ticks_do_not_resend_unchanged_state(self, controller):
        seen = []
        controller.on("right_joystick", lambda ctrl: seen.append(ctrl))
        controller._mark_stick_dirty("right_joystick")

        controller._control_tick()
        controller._control_tick()
        controller._control_tick()

        assert len(seen) == 1

    def test_many_events_collapse_into_one_dispatch(
        self, monkeypatch, controller, no_control_thread
    ):
        seen = []
        controller.on("left_joystick", lambda ctrl: seen.append(ctrl.l_left))

        _read_events(
            monkeypatch,
            controller,
            [_event(EV_ABS, LEFT_STICK_X, v) for v in (200, 220, 240, 255)],
        )
        controller._control_tick()

        assert len(seen) == 1

    def test_the_latest_position_wins(
        self, monkeypatch, controller, no_control_thread
    ):
        """Coalescing must never lose the final stick position."""
        seen = []
        controller.on("left_joystick", lambda ctrl: seen.append(ctrl.l_left))

        _read_events(
            monkeypatch,
            controller,
            [_event(EV_ABS, LEFT_STICK_X, v) for v in (255, 200, 128)],
        )
        controller._control_tick()

        assert seen == [pytest.approx(0, abs=100)]

    def test_a_release_to_centre_is_always_delivered(
        self, monkeypatch, controller, no_control_thread
    ):
        """The stop command must not be the one that gets dropped."""
        seen = []
        controller.on("left_joystick", lambda ctrl: seen.append(ctrl.l_left))

        _read_events(
            monkeypatch,
            controller,
            [_event(EV_ABS, LEFT_STICK_X, 255), _event(EV_ABS, LEFT_STICK_X, 128)],
        )
        controller._control_tick()

        assert seen[-1] == 0

    def test_both_sticks_dispatch_in_one_tick(self, controller):
        seen = []
        controller.on("left_joystick", lambda ctrl: seen.append("l"))
        controller.on("right_joystick", lambda ctrl: seen.append("r"))
        controller._mark_stick_dirty("left_joystick")
        controller._mark_stick_dirty("right_joystick")

        assert controller._control_tick() == 2
        assert sorted(seen) == ["l", "r"]

    def test_movement_during_a_tick_is_not_lost(self, controller):
        """The dirty flag clears before dispatch, so a stick moved while the
        callback runs is picked up next tick rather than cleared unseen."""
        seen = []

        def move_again(ctrl):
            seen.append(ctrl)
            if len(seen) == 1:
                ctrl._mark_stick_dirty("left_joystick")

        controller.on("left_joystick", move_again)
        controller._mark_stick_dirty("left_joystick")

        controller._control_tick()
        assert controller._left_dirty is True

        controller._control_tick()
        assert len(seen) == 2


class TestReaderInstrumentation:

    def test_read_and_processing_are_timed_per_event(
        self, monkeypatch, controller, no_control_thread
    ):
        recorded = []
        controller.set_diagnostics(_RecordingDiagnostics(recorded))

        _read_events(
            monkeypatch,
            controller,
            [_event(EV_ABS, LEFT_STICK_X, 200), _event(EV_ABS, LEFT_STICK_X, 210)],
        )

        assert len(recorded) == 2
        assert all(entry["read_ms"] is not None for entry in recorded)
        assert all(entry["proc_ms"] is not None for entry in recorded)

    def test_the_first_event_has_no_preceding_gap(
        self, monkeypatch, controller, no_control_thread
    ):
        recorded = []
        controller.set_diagnostics(_RecordingDiagnostics(recorded))

        _read_events(
            monkeypatch,
            controller,
            [_event(EV_ABS, LEFT_STICK_X, 200), _event(EV_ABS, LEFT_STICK_X, 210)],
        )

        assert recorded[0]["gap_ms"] is None
        assert recorded[1]["gap_ms"] is not None

    def test_event_lag_is_passed_through_to_classify_the_read(
        self, monkeypatch, controller, no_control_thread
    ):
        recorded = []
        diagnostics = _RecordingDiagnostics(recorded, lag_ms=350.0)
        controller.set_diagnostics(diagnostics)

        _read_events(monkeypatch, controller, [_event(EV_ABS, LEFT_STICK_X, 200)])

        assert recorded[0]["lag_ms"] == 350.0

    def test_syn_dropped_records_a_stall(
        self, monkeypatch, controller, no_control_thread
    ):
        recorded = []
        diagnostics = _RecordingDiagnostics(recorded)
        controller.set_diagnostics(diagnostics)

        _read_events(
            monkeypatch,
            controller,
            [_event(EV_ABS, LEFT_STICK_X, 200), _event(0, 3, 0)],
        )

        assert len(diagnostics.stalls) == 1

    def test_an_ordinary_syn_does_not_record_a_stall(
        self, monkeypatch, controller, no_control_thread
    ):
        recorded = []
        diagnostics = _RecordingDiagnostics(recorded)
        controller.set_diagnostics(diagnostics)

        # EV_SYN code 0 is SYN_REPORT, which ends every normal event batch.
        _read_events(monkeypatch, controller, [_event(0, 0, 0)])

        assert diagnostics.stalls == []

    def test_reading_works_with_no_diagnostics_attached(
        self, monkeypatch, controller, no_control_thread
    ):
        _read_events(monkeypatch, controller, [_event(EV_ABS, LEFT_STICK_X, 200)])

        assert controller.l_left != 0


class TestControlRate:

    def test_defaults_to_30hz(self, controller):
        assert DEFAULT_CONTROL_LOOP_HZ == 30
        assert controller._control_interval == pytest.approx(1.0 / 30)

    def test_rate_is_configurable(self, controller):
        controller.set_control_rate(20)

        assert controller._control_interval == pytest.approx(0.05)

    def test_rejects_a_nonpositive_rate(self, controller):
        with pytest.raises(ValueError):
            controller.set_control_rate(0)


class TestControlLoopLifecycle:

    def test_loop_stops_when_the_read_loop_ends(self, monkeypatch, controller):
        _read_events(monkeypatch, controller, [_event(EV_ABS, LEFT_STICK_X, 200)])

        assert controller._control_running is False
        assert controller._control_thread is None

    def test_loop_stops_when_the_read_loop_raises(self, monkeypatch, controller):
        def explode(_ctrl):
            raise TypeError("boom")

        controller.on("cross_button", explode)
        _read_events(monkeypatch, controller, [_event(EV_KEY, CROSS_BUTTON, 1)])

        assert controller._control_running is False

    def test_loop_exits_on_stop(self, controller):
        controller._control_running = True
        controller.stop()

        assert controller.stopped is True
        assert controller._control_running is False

    def test_control_loop_can_be_stopped_without_stopping_the_reader(self, controller):
        """Shutdown halts motor commands before the motors are stopped."""
        controller._control_running = True
        controller.stop_control_loop()

        assert controller._control_running is False
        assert controller.stopped is False

    def test_stop_joins_the_control_thread(self, controller):
        """Signalling alone would let an in-flight tick issue a motor command
        after the motors have been stopped."""
        joined = []
        thread = type("T", (), {
            "is_alive": lambda self: True,
            "join": lambda self, timeout=None: joined.append(timeout),
        })()
        controller._control_thread = thread
        controller._control_running = True

        controller.stop_control_loop(timeout=1.5)

        assert joined == [1.5]
        assert controller._control_thread is None

    def test_stop_is_safe_when_no_thread_was_started(self, controller):
        controller.stop_control_loop()

        assert controller._control_running is False

    def test_stop_survives_a_thread_without_join(self, controller):
        """Pybricks MicroPython's Thread has neither is_alive nor join."""
        controller._control_thread = type("MicroPythonThread", (), {})()
        controller._control_running = True

        controller.stop_control_loop()

        assert controller._control_thread is None

    def test_no_dispatch_after_the_control_loop_is_stopped(self, controller):
        seen = []
        controller.on("left_joystick", lambda ctrl: seen.append(ctrl))
        controller._control_running = True
        controller._mark_stick_dirty("left_joystick")
        controller.stop_control_loop()

        controller._control_loop()

        assert seen == []

    def test_a_failing_callback_does_not_kill_the_loop(self, controller):
        calls = []

        def explode(ctrl):
            calls.append(True)
            raise TypeError("can't convert float to int")

        controller.on("left_joystick", explode)
        controller._mark_stick_dirty("left_joystick")

        # _control_tick lets it propagate; _control_loop is what must survive.
        with pytest.raises(TypeError):
            controller._control_tick()

        controller._control_running = True
        controller._mark_stick_dirty("left_joystick")

        def stop_after_one_pass(_interval):
            controller._control_running = False

        import robot_controllers.ps4_controller as module
        original_sleep = module._sleep
        module._sleep = stop_after_one_pass
        try:
            controller._control_loop()
        finally:
            module._sleep = original_sleep

        assert len(calls) == 2
