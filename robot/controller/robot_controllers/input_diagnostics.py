#!/usr/bin/env pybricks-micropython

"""
Instrumentation for the PlayStation controller input path.

Answers three questions about controller unresponsiveness without changing
any control behaviour:

1. *Is the kernel dropping our events?*  Linux gives each open
   ``/dev/input/event*`` file descriptor a small fixed ring buffer.  When a
   reader stops draining it for long enough the kernel discards events and
   injects an ``EV_SYN``/``SYN_DROPPED`` marker.  Every dropped event is a
   button press or stick position the robot will never see.
   :meth:`InputDiagnostics.record_event` counts those markers.

2. *How stale is the event we are acting on?*  Every evdev event carries the
   kernel's ``CLOCK_REALTIME`` timestamp of when the input actually
   happened, which the read loop has always unpacked and discarded.
   Comparing it against the wall clock at processing time gives the true
   end-to-end input latency, queueing delay included.

3. *What stopped the reader thread?*  An exception raised by a callback
   propagates out of ``EventHandler.trigger()`` and terminates
   ``PS4Controller.run()`` for the rest of the session, leaving a robot that
   still answers the network remote but ignores the gamepad entirely.
   :meth:`InputDiagnostics.record_loop_exit` captures the cause and the
   report thread keeps restating it so it cannot scroll away unnoticed.

Reporting runs on its own thread so the periodic summary — which does
blocking ``print()`` I/O — never runs on the read loop it is measuring.
Recording is a handful of arithmetic operations plus one lock acquisition
per event, which at observed gamepad event rates is a fraction of a percent
of the read loop's time.

Usage::

    diagnostics = InputDiagnostics()
    controller.set_diagnostics(diagnostics)
    diagnostics.start()
    # ... drive the robot, reproduce the fault ...
    diagnostics.stop()
"""

import threading

from threading_compat import create_lock

try:
    from time import time as _time
except ImportError:  # pragma: no cover - MicroPython builds without time.time
    _time = None

from time import sleep as _sleep

# EV_SYN code 3 (SYN_DROPPED) is the kernel telling us its per-fd event
# buffer overflowed and events were discarded before we read them.
EV_SYN_TYPE = 0
SYN_DROPPED_CODE = 3

DEFAULT_REPORT_INTERVAL_S = 10.0

# A dispatch slower than this starves the read loop long enough to risk an
# evdev buffer overflow, so these are counted separately from the average.
DEFAULT_SLOW_DISPATCH_MS = 50.0

# An event older than this by the time we process it was queued behind
# something, i.e. the robot is reacting to stale input.
DEFAULT_STALE_EVENT_MS = 100.0

# Granularity of the reporting thread's sleep, so stop() returns promptly
# instead of waiting out a whole reporting interval.
_STOP_POLL_INTERVAL_S = 0.5


class InputDiagnostics:
    """Collect and periodically report controller input-path health metrics.

    Parameters
    ----------
    report_interval:
        Seconds between summary reports from the reporting thread.
    slow_dispatch_ms:
        Callback durations at or above this are counted as slow.
    stale_event_ms:
        Event lags at or above this are counted as stale.
    printer:
        Output function for reports (defaults to ``print``).  Overridable so
        tests can capture reports without touching stdout.
    clock:
        Zero-argument function returning wall-clock seconds as a float
        (defaults to ``time.time``).  Overridable so tests can produce
        deterministic timings.
    """

    def __init__(
        self,
        report_interval=DEFAULT_REPORT_INTERVAL_S,
        slow_dispatch_ms=DEFAULT_SLOW_DISPATCH_MS,
        stale_event_ms=DEFAULT_STALE_EVENT_MS,
        printer=None,
        clock=None,
    ):
        self.report_interval = report_interval
        self.slow_dispatch_ms = slow_dispatch_ms
        self.stale_event_ms = stale_event_ms
        self._printer = printer if printer is not None else print
        self._clock = clock if clock is not None else _time

        self._lock = create_lock()
        self._report_thread = None
        self._running = False

        # Cumulative since start; never reset.
        self._syn_dropped_total = 0
        self._events_total = 0

        self._loop_exit = None
        self._reset_window(started_at=self._now())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def now(self):
        """Return wall-clock seconds, or ``None`` when unavailable.

        Exposed so instrumented code times itself against the same clock the
        diagnostics use, rather than importing its own and risking a
        mismatch — and so a MicroPython build without ``time.time()`` has a
        single place that degrades to ``None``.
        """
        if self._clock is None:
            return None
        try:
            return self._clock()
        except Exception:  # noqa: BLE001 - diagnostics must never raise
            return None

    def _now(self):
        return self.now()

    def _reset_window(self, started_at):
        """Start a fresh reporting window.  Caller must hold ``_lock``
        (or be in ``__init__``, before any other thread can see us)."""
        self._window_started_at = started_at
        self._window_events = 0
        self._window_syn_dropped = 0
        self._window_lag_samples = 0
        self._window_lag_total_ms = 0.0
        self._window_lag_max_ms = 0.0
        self._window_stale_events = 0
        # event name -> [count, total_ms, max_ms, slow_count, error_count]
        self._window_dispatch = {}
        # event name -> count of raw events folded into pending state
        self._window_coalesced = {}
        # raw axis value -> count of times it was discarded as a sentinel
        self._window_axis_rejected = {}

    # ------------------------------------------------------------------
    # Recording API - called from the controller read loop
    # ------------------------------------------------------------------

    def record_event(self, ev_type, code, tv_sec=None, tv_usec=None):
        """Record one raw evdev event.

        *tv_sec*/*tv_usec* are the kernel timestamp fields straight from the
        unpacked event; when supplied they are used to compute how stale the
        event was by the time it reached us.
        """
        lag_ms = None
        if tv_sec is not None and tv_usec is not None:
            now = self._now()
            if now is not None:
                lag_ms = (now - (tv_sec + tv_usec / 1000000.0)) * 1000.0
                # A negative lag means the kernel and our clock disagree
                # (evdev can be switched to a monotonic clock), in which case
                # the absolute value is meaningless -- discard rather than
                # skew the average.
                if lag_ms < 0:
                    lag_ms = None

        is_syn_dropped = (ev_type == EV_SYN_TYPE and code == SYN_DROPPED_CODE)

        with self._lock:
            self._events_total += 1
            self._window_events += 1

            if is_syn_dropped:
                self._syn_dropped_total += 1
                self._window_syn_dropped += 1

            if lag_ms is not None:
                self._window_lag_samples += 1
                self._window_lag_total_ms += lag_ms
                if lag_ms > self._window_lag_max_ms:
                    self._window_lag_max_ms = lag_ms
                if lag_ms >= self.stale_event_ms:
                    self._window_stale_events += 1

    def record_dispatch(self, event_name, duration_ms, failed=False):
        """Record how long one callback dispatch took, in milliseconds."""
        with self._lock:
            stats = self._window_dispatch.get(event_name)
            if stats is None:
                stats = [0, 0.0, 0.0, 0, 0]
                self._window_dispatch[event_name] = stats
            stats[0] += 1
            stats[1] += duration_ms
            if duration_ms > stats[2]:
                stats[2] = duration_ms
            if duration_ms >= self.slow_dispatch_ms:
                stats[3] += 1
            if failed:
                stats[4] += 1

    def record_coalesced(self, event_name):
        """Record a stick event folded into the pending control-loop state.

        Reported against the matching ``dispatch`` count so the coalescing
        ratio is visible: a large gap between the two is the mechanism that
        keeps the read loop ahead of the incoming event rate.
        """
        with self._lock:
            self._window_coalesced[event_name] = (
                self._window_coalesced.get(event_name, 0) + 1
            )

    def record_axis_rejected(self, value):
        """Record a raw axis value discarded as a release sentinel."""
        with self._lock:
            self._window_axis_rejected[value] = (
                self._window_axis_rejected.get(value, 0) + 1
            )

    def record_loop_exit(self, reason, exception=None, last_event=None):
        """Record that the controller read loop has terminated.

        Once set, every subsequent report restates this, because a dead read
        loop is the difference between "some inputs are dropped" and "the
        gamepad is inert until the robot is restarted".
        """
        detail = str(reason)
        if exception is not None:
            detail += ": {} - {}".format(type(exception).__name__, exception)
        if last_event is not None:
            detail += " (last event: {})".format(last_event)
        with self._lock:
            self._loop_exit = detail

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def snapshot(self, reset=False):
        """Return the current window's metrics as a dict.

        When *reset* is true a new window is started, so the caller receives
        per-window rather than cumulative figures.
        """
        now = self._now()
        with self._lock:
            elapsed = None
            if now is not None and self._window_started_at is not None:
                elapsed = now - self._window_started_at

            avg_lag_ms = None
            if self._window_lag_samples:
                avg_lag_ms = self._window_lag_total_ms / self._window_lag_samples

            # Deep-copy the per-name stat lists so a caller mutating the
            # snapshot cannot corrupt the live counters.
            dispatch = {}
            for name, stats in self._window_dispatch.items():
                dispatch[name] = list(stats)

            data = {
                "elapsed_s": elapsed,
                "events": self._window_events,
                "events_total": self._events_total,
                "syn_dropped": self._window_syn_dropped,
                "syn_dropped_total": self._syn_dropped_total,
                "lag_avg_ms": avg_lag_ms,
                "lag_max_ms": self._window_lag_max_ms if self._window_lag_samples else None,
                "stale_events": self._window_stale_events,
                "dispatch": dispatch,
                "coalesced": self._window_coalesced.copy(),
                "axis_rejected": self._window_axis_rejected.copy(),
                "loop_exit": self._loop_exit,
            }

            if reset:
                self._reset_window(started_at=now)

        return data

    def format_report(self, data):
        """Render a :meth:`snapshot` dict as printable lines."""
        lines = []
        elapsed = data.get("elapsed_s")
        if elapsed is None:
            lines.append("=== PS4 input diagnostics ===")
        else:
            lines.append("=== PS4 input diagnostics (window %.1fs) ===" % elapsed)

        rate = ""
        if elapsed:
            rate = " (%.0f/s)" % (data["events"] / elapsed)
        lines.append(
            "events: {}{}  total: {}".format(
                data["events"], rate, data["events_total"]
            )
        )

        if data["syn_dropped"]:
            lines.append(
                "SYN_DROPPED: {} this window, {} total"
                " -- KERNEL DISCARDED EVENTS, INPUT WAS LOST".format(
                    data["syn_dropped"], data["syn_dropped_total"]
                )
            )
        else:
            lines.append(
                "SYN_DROPPED: 0 this window, {} total".format(
                    data["syn_dropped_total"]
                )
            )

        if data["lag_avg_ms"] is None:
            lines.append("event lag: no samples")
        else:
            lines.append(
                "event lag: avg %.1fms max %.1fms  stale(>=%.0fms): %d"
                % (
                    data["lag_avg_ms"],
                    data["lag_max_ms"],
                    self.stale_event_ms,
                    data["stale_events"],
                )
            )

        dispatch = data["dispatch"]
        if dispatch:
            # Worst max-duration first: the slowest callback is the one most
            # likely to have starved the read loop into an overflow.
            ordered = sorted(
                dispatch.items(), key=lambda item: item[1][2], reverse=True
            )
            coalesced = data.get("coalesced") or {}
            for name, stats in ordered:
                count, total_ms, max_ms, slow_count, error_count = stats
                avg_ms = total_ms / count if count else 0.0
                line = "dispatch %-16s n=%-5d avg %.1fms max %.1fms slow=%d" % (
                    name,
                    count,
                    avg_ms,
                    max_ms,
                    slow_count,
                )
                folded = coalesced.get(name)
                if folded:
                    line += " (from %d events, %.1fx)" % (
                        folded,
                        float(folded) / count if count else 0.0,
                    )
                if error_count:
                    line += " ERRORS=%d" % error_count
                lines.append(line)

        rejected = data["axis_rejected"]
        if rejected:
            parts = [
                "{}x{}".format(count, value)
                for value, count in sorted(rejected.items())
            ]
            lines.append(
                "axis values discarded as sentinel: " + ", ".join(parts)
            )

        if data["loop_exit"]:
            lines.append(
                "READ LOOP IS DEAD - gamepad inert until restart: {}".format(
                    data["loop_exit"]
                )
            )

        lines.append("=" * 44)
        return lines

    def report_once(self, reset=True):
        """Print one summary report.  Returns the snapshot that was printed."""
        data = self.snapshot(reset=reset)
        # Printing happens outside the lock: on the EV3 stdout is an SSH pipe
        # or the LCD console, either of which can block, and holding the lock
        # across that would stall the read loop we are trying to measure.
        for line in self.format_report(data):
            try:
                self._printer(line)
            except Exception:  # noqa: BLE001 - diagnostics must never raise
                break
        return data

    # ------------------------------------------------------------------
    # Reporting thread lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the background reporting thread."""
        if self._running:
            return
        self._running = True
        # Pybricks MicroPython's Thread() accepts only ``target`` - passing
        # ``daemon``/``name`` raises TypeError (PEN-188).
        self._report_thread = threading.Thread(target=self._report_loop)
        self._report_thread.start()

    def stop(self):
        """Stop the reporting thread and print a final report."""
        was_running = self._running
        self._running = False
        if was_running:
            self.report_once(reset=False)

    def is_running(self):
        return self._running

    def _report_loop(self):
        while self._running:
            waited = 0.0
            while self._running and waited < self.report_interval:
                _sleep(_STOP_POLL_INTERVAL_S)
                waited += _STOP_POLL_INTERVAL_S
            if not self._running:
                break
            try:
                self.report_once()
            except Exception:  # noqa: BLE001 - never kill the reporting thread
                pass
