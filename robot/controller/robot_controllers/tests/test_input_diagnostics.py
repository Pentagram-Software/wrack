#!/usr/bin/env python3

"""
Unit tests for InputDiagnostics and its PS4Controller integration.
"""

import struct

import pytest

from robot_controllers import InputDiagnostics, PS4Controller
from robot_controllers.input_diagnostics import (
    EV_SYN_TYPE,
    SYN_DROPPED_CODE,
)


class FakeClock:
    """Deterministic monotonically-advancing clock."""

    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def lines():
    return []


@pytest.fixture
def diagnostics(clock, lines):
    return InputDiagnostics(
        report_interval=1.0,
        printer=lines.append,
        clock=clock,
    )


class TestEventRecording:

    def test_counts_events(self, diagnostics):
        for _ in range(5):
            diagnostics.record_event(3, 0)

        data = diagnostics.snapshot()
        assert data["events"] == 5
        assert data["events_total"] == 5

    def test_counts_syn_dropped_separately(self, diagnostics):
        diagnostics.record_event(3, 0)
        diagnostics.record_event(EV_SYN_TYPE, SYN_DROPPED_CODE)
        diagnostics.record_event(EV_SYN_TYPE, SYN_DROPPED_CODE)

        data = diagnostics.snapshot()
        assert data["events"] == 3
        assert data["syn_dropped"] == 2

    def test_syn_report_event_is_not_counted_as_dropped(self, diagnostics):
        # EV_SYN code 0 is SYN_REPORT, emitted after every normal event
        # packet -- only code 3 (SYN_DROPPED) signals an overflow.
        diagnostics.record_event(EV_SYN_TYPE, 0)

        assert diagnostics.snapshot()["syn_dropped"] == 0

    def test_computes_event_lag_from_kernel_timestamp(self, diagnostics, clock):
        clock.now = 1000.5
        diagnostics.record_event(3, 0, tv_sec=1000, tv_usec=0)

        data = diagnostics.snapshot()
        assert data["lag_avg_ms"] == pytest.approx(500.0)
        assert data["lag_max_ms"] == pytest.approx(500.0)

    def test_counts_stale_events_over_threshold(self, clock, lines):
        diagnostics = InputDiagnostics(
            stale_event_ms=100.0, printer=lines.append, clock=clock
        )
        clock.now = 1000.05
        diagnostics.record_event(3, 0, tv_sec=1000, tv_usec=0)  # 50ms - fresh
        clock.now = 1000.30
        diagnostics.record_event(3, 0, tv_sec=1000, tv_usec=0)  # 300ms - stale

        data = diagnostics.snapshot()
        assert data["stale_events"] == 1
        assert data["lag_max_ms"] == pytest.approx(300.0)

    def test_negative_lag_is_discarded(self, diagnostics, clock):
        # evdev can be switched to a monotonic clock, making kernel
        # timestamps incomparable with time.time(); a negative result means
        # the two clocks disagree, so the sample is meaningless.
        clock.now = 1000.0
        diagnostics.record_event(3, 0, tv_sec=5000, tv_usec=0)

        data = diagnostics.snapshot()
        assert data["lag_avg_ms"] is None
        assert data["events"] == 1

    def test_lag_not_computed_without_timestamp(self, diagnostics):
        diagnostics.record_event(3, 0)

        assert diagnostics.snapshot()["lag_avg_ms"] is None


class TestDispatchRecording:

    def test_aggregates_per_event_name(self, diagnostics):
        diagnostics.record_dispatch("left_joystick", 1.0)
        diagnostics.record_dispatch("left_joystick", 3.0)

        count, total_ms, max_ms, slow, errors = (
            diagnostics.snapshot()["dispatch"]["left_joystick"]
        )
        assert count == 2
        assert total_ms == pytest.approx(4.0)
        assert max_ms == pytest.approx(3.0)
        assert slow == 0
        assert errors == 0

    def test_counts_slow_dispatches(self, clock, lines):
        diagnostics = InputDiagnostics(
            slow_dispatch_ms=50.0, printer=lines.append, clock=clock
        )
        diagnostics.record_dispatch("cross_button", 10.0)
        diagnostics.record_dispatch("cross_button", 2100.0)

        stats = diagnostics.snapshot()["dispatch"]["cross_button"]
        assert stats[3] == 1
        assert stats[2] == pytest.approx(2100.0)

    def test_counts_failed_dispatches(self, diagnostics):
        diagnostics.record_dispatch("move", 1.0, failed=True)

        assert diagnostics.snapshot()["dispatch"]["move"][4] == 1


class TestReaderTiming:
    """Separates 'idle, waiting for input' from 'starved: data was already
    waiting'. Both look like time inside read(); only the staleness of the
    event that read returned tells them apart."""

    def test_a_read_returning_a_fresh_event_is_idle_time(self, diagnostics):
        diagnostics.record_reader_timing(read_ms=500.0, lag_ms=2.0)

        data = diagnostics.snapshot()
        assert data["read_fresh"] == [1, 500.0, 500.0]
        assert data["read_stale"][0] == 0

    def test_a_read_returning_a_stale_event_is_starvation(self, diagnostics):
        diagnostics.record_reader_timing(read_ms=500.0, lag_ms=400.0)

        data = diagnostics.snapshot()
        assert data["read_stale"] == [1, 500.0, 500.0]
        assert data["read_fresh"][0] == 0

    def test_unknown_lag_counts_as_idle_rather_than_starved(self, diagnostics):
        diagnostics.record_reader_timing(read_ms=10.0, lag_ms=None)

        assert diagnostics.snapshot()["read_fresh"][0] == 1

    def test_processing_and_gap_are_tracked_separately(self, diagnostics):
        diagnostics.record_reader_timing(read_ms=1.0, proc_ms=4.0, gap_ms=0.5)

        data = diagnostics.snapshot()
        assert data["proc"] == [1, 4.0, 4.0]
        assert data["gap"] == [1, 0.5, 0.5]

    def test_maxima_are_kept(self, diagnostics):
        diagnostics.record_reader_timing(read_ms=5.0, lag_ms=0.0)
        diagnostics.record_reader_timing(read_ms=90.0, lag_ms=0.0)
        diagnostics.record_reader_timing(read_ms=20.0, lag_ms=0.0)

        assert diagnostics.snapshot()["read_fresh"] == [3, 115.0, 90.0]

    def test_timings_reset_with_the_window(self, diagnostics):
        diagnostics.record_reader_timing(read_ms=5.0, proc_ms=1.0, lag_ms=0.0)
        diagnostics.snapshot(reset=True)

        data = diagnostics.snapshot()
        assert data["read_fresh"][0] == 0
        assert data["proc"][0] == 0

    def test_report_flags_the_starved_bucket(self, diagnostics, lines):
        diagnostics.record_reader_timing(read_ms=400.0, proc_ms=1.0, lag_ms=300.0)
        diagnostics.report_once()

        starved = [line for line in lines if "read->stale" in line]
        assert len(starved) == 1
        assert "STARVED" in starved[0]

    def test_report_omits_the_breakdown_without_samples(self, diagnostics, lines):
        diagnostics.report_once()

        assert not any("reader:" in line for line in lines)


class TestDropStalls:

    def test_stall_lengths_are_recorded(self, diagnostics):
        diagnostics.record_drop_stall(120.0)
        diagnostics.record_drop_stall(880.0)

        assert diagnostics.snapshot()["drop_stall"] == [2, 1000.0, 880.0]

    def test_report_shows_stalls(self, diagnostics, lines):
        diagnostics.record_drop_stall(500.0)
        diagnostics.record_reader_timing(read_ms=1.0, lag_ms=0.0)
        diagnostics.report_once()

        assert any("SYN_DROPPED stalls: n=1" in line for line in lines)


class TestCoalescing:

    def test_counts_events_folded_per_stick(self, diagnostics):
        for _ in range(40):
            diagnostics.record_coalesced("left_joystick")
        diagnostics.record_coalesced("right_joystick")

        assert diagnostics.snapshot()["coalesced"] == {
            "left_joystick": 40,
            "right_joystick": 1,
        }

    def test_report_shows_the_coalescing_ratio(self, diagnostics, lines):
        for _ in range(40):
            diagnostics.record_coalesced("left_joystick")
        for _ in range(4):
            diagnostics.record_dispatch("left_joystick", 10.0)
        diagnostics.report_once()

        dispatch_line = next(
            line for line in lines if line.startswith("dispatch ")
        )
        assert "from 40 events" in dispatch_line
        assert "10.0x" in dispatch_line

    def test_coalesced_counts_reset_with_the_window(self, diagnostics):
        diagnostics.record_coalesced("left_joystick")
        diagnostics.snapshot(reset=True)

        assert diagnostics.snapshot()["coalesced"] == {}


class TestAxisRejection:

    def test_counts_rejections_per_raw_value(self, diagnostics):
        diagnostics.record_axis_rejected(4294967295)
        diagnostics.record_axis_rejected(4294967295)
        diagnostics.record_axis_rejected(4294967294)

        rejected = diagnostics.snapshot()["axis_rejected"]
        assert rejected == {4294967295: 2, 4294967294: 1}


class TestLoopExit:

    def test_records_reason_and_exception(self, diagnostics):
        diagnostics.record_loop_exit(
            "unhandled exception in read loop",
            exception=TypeError("can't convert float to int"),
            last_event="type=3 code=0 value=255",
        )

        exit_detail = diagnostics.snapshot()["loop_exit"]
        assert "unhandled exception in read loop" in exit_detail
        assert "TypeError" in exit_detail
        assert "can't convert float to int" in exit_detail
        assert "type=3 code=0 value=255" in exit_detail

    def test_loop_exit_survives_window_reset(self, diagnostics):
        diagnostics.record_loop_exit("device reported EOF")
        diagnostics.snapshot(reset=True)

        assert diagnostics.snapshot()["loop_exit"] == "device reported EOF"

    def test_report_flags_dead_loop(self, diagnostics, lines):
        diagnostics.record_loop_exit("device reported EOF")
        diagnostics.report_once()

        assert any("READ LOOP IS DEAD" in line for line in lines)


class TestWindowing:

    def test_reset_clears_window_but_keeps_totals(self, diagnostics):
        diagnostics.record_event(EV_SYN_TYPE, SYN_DROPPED_CODE)
        diagnostics.record_dispatch("move", 1.0)
        diagnostics.snapshot(reset=True)

        data = diagnostics.snapshot()
        assert data["events"] == 0
        assert data["syn_dropped"] == 0
        assert data["dispatch"] == {}
        assert data["events_total"] == 1
        assert data["syn_dropped_total"] == 1

    def test_elapsed_tracks_window_start(self, diagnostics, clock):
        clock.advance(7.5)

        assert diagnostics.snapshot()["elapsed_s"] == pytest.approx(7.5)


class TestReportFormatting:

    def test_report_highlights_dropped_events(self, diagnostics, lines):
        diagnostics.record_event(EV_SYN_TYPE, SYN_DROPPED_CODE)
        diagnostics.report_once()

        assert any("KERNEL DISCARDED EVENTS" in line for line in lines)

    def test_report_orders_dispatch_by_worst_max(self, diagnostics, lines):
        diagnostics.record_dispatch("left_joystick", 2.0)
        diagnostics.record_dispatch("cross_button", 2100.0)
        diagnostics.report_once()

        dispatch_lines = [line for line in lines if line.startswith("dispatch ")]
        assert "cross_button" in dispatch_lines[0]
        assert "left_joystick" in dispatch_lines[1]

    def test_report_survives_a_failing_printer(self, clock):
        def boom(_line):
            raise OSError("stdout pipe is full")

        diagnostics = InputDiagnostics(printer=boom, clock=clock)
        diagnostics.record_event(3, 0)

        diagnostics.report_once()  # must not raise

    def test_snapshot_dispatch_is_a_copy(self, diagnostics):
        diagnostics.record_dispatch("move", 1.0)
        data = diagnostics.snapshot()
        data["dispatch"]["move"][0] = 999

        assert diagnostics.snapshot()["dispatch"]["move"][0] == 1


class TestClocklessRuntime:
    """MicroPython builds may not expose time.time()."""

    def test_records_without_a_clock(self, lines):
        diagnostics = InputDiagnostics(printer=lines.append, clock=lambda: None)
        diagnostics.record_event(3, 0, tv_sec=1000, tv_usec=0)

        data = diagnostics.snapshot()
        assert data["events"] == 1
        assert data["lag_avg_ms"] is None
        assert data["elapsed_s"] is None

    def test_reports_without_a_clock(self, lines):
        diagnostics = InputDiagnostics(printer=lines.append, clock=lambda: None)
        diagnostics.record_event(3, 0)
        diagnostics.report_once()

        assert any("PS4 input diagnostics" in line for line in lines)

    def test_a_raising_clock_never_propagates(self, lines):
        def broken_clock():
            raise AttributeError("no time on this build")

        diagnostics = InputDiagnostics(printer=lines.append, clock=broken_clock)
        diagnostics.record_event(3, 0, tv_sec=1000, tv_usec=0)

        assert diagnostics.snapshot()["events"] == 1


class TestControllerIntegration:

    @pytest.fixture
    def controller(self):
        return PS4Controller()

    def test_dispatch_without_diagnostics_still_triggers(self, controller):
        fired = []
        controller.on("cross_button", lambda ctrl: fired.append(ctrl))

        controller._dispatch("cross_button")

        assert len(fired) == 1

    def test_dispatch_times_the_callback(self, controller, diagnostics, clock):
        controller.set_diagnostics(diagnostics)
        controller.on("cross_button", lambda ctrl: clock.advance(2.0))

        controller._dispatch("cross_button")

        stats = diagnostics.snapshot()["dispatch"]["cross_button"]
        assert stats[0] == 1
        assert stats[2] == pytest.approx(2000.0)

    def test_dispatch_records_and_reraises_callback_errors(
        self, controller, diagnostics
    ):
        def explode(_ctrl):
            raise TypeError("can't convert float to int")

        controller.set_diagnostics(diagnostics)
        controller.on("left_joystick", explode)

        with pytest.raises(TypeError):
            controller._dispatch("left_joystick")

        assert diagnostics.snapshot()["dispatch"]["left_joystick"][4] == 1

    def test_scale_axis_records_rejected_sentinel(self, controller, diagnostics):
        controller.set_diagnostics(diagnostics)

        assert controller._scale_axis(4294967295, (-100, 100)) is None
        assert diagnostics.snapshot()["axis_rejected"] == {4294967295: 1}

    def test_scale_axis_records_nothing_for_valid_values(
        self, controller, diagnostics
    ):
        controller.set_diagnostics(diagnostics)
        controller._scale_axis(128, (-100, 100))

        assert diagnostics.snapshot()["axis_rejected"] == {}

    def test_set_diagnostics_none_detaches(self, controller, diagnostics):
        controller.set_diagnostics(diagnostics)
        controller.set_diagnostics(None)
        controller._dispatch("cross_button")

        assert diagnostics.snapshot()["dispatch"] == {}


class TestReadLoopInstrumentation:
    """Drive PS4Controller.run() over a scripted event stream."""

    FORMAT = 'llHHI'

    @classmethod
    def _event(cls, ev_type, code, value, tv_sec=1000, tv_usec=0):
        return struct.pack(cls.FORMAT, tv_sec, tv_usec, ev_type, code, value)

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

    def _run_with_events(self, monkeypatch, controller, payloads):
        device = self._FakeDeviceFile(payloads)
        monkeypatch.setattr(
            "robot_controllers.ps4_controller.find_controller_device",
            lambda: "/dev/input/event4",
        )
        monkeypatch.setattr(
            "robot_controllers.ps4_controller.open", lambda *a, **k: device,
            raising=False,
        )
        controller.run()
        return device

    @pytest.fixture
    def controller(self):
        return PS4Controller()

    def test_records_every_event(self, monkeypatch, controller, diagnostics):
        controller.set_diagnostics(diagnostics)
        self._run_with_events(
            monkeypatch,
            controller,
            [self._event(1, 304, 1), self._event(0, 0, 0)],
        )

        assert diagnostics.snapshot()["events"] == 2

    def test_records_syn_dropped_from_the_stream(
        self, monkeypatch, controller, diagnostics
    ):
        controller.set_diagnostics(diagnostics)
        self._run_with_events(
            monkeypatch,
            controller,
            [self._event(EV_SYN_TYPE, SYN_DROPPED_CODE, 0)],
        )

        assert diagnostics.snapshot()["syn_dropped"] == 1

    def test_records_clean_exit_on_eof(self, monkeypatch, controller, diagnostics):
        controller.set_diagnostics(diagnostics)
        self._run_with_events(monkeypatch, controller, [self._event(1, 304, 1)])

        assert "EOF" in diagnostics.snapshot()["loop_exit"]

    def test_records_the_exception_that_kills_the_loop(
        self, monkeypatch, controller, diagnostics
    ):
        def explode(_ctrl):
            raise TypeError("can't convert float to int")

        controller.set_diagnostics(diagnostics)
        controller.on("cross_button", explode)
        self._run_with_events(monkeypatch, controller, [self._event(1, 304, 1)])

        exit_detail = diagnostics.snapshot()["loop_exit"]
        assert "TypeError" in exit_detail
        assert "type=1 code=304 value=1" in exit_detail

    def test_run_loop_is_unaffected_without_diagnostics(
        self, monkeypatch, controller
    ):
        fired = []
        controller.on("cross_button", lambda ctrl: fired.append(ctrl))
        device = self._run_with_events(
            monkeypatch, controller, [self._event(1, 304, 1)]
        )

        assert len(fired) == 1
        assert device.closed
