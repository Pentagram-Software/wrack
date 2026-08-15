#!/usr/bin/env pybricks-micropython

"""Run slow, non-time-critical actions off the caller's thread.

Some robot actions take seconds: ``ev3.speaker.say()`` was measured at 5-7
seconds on-device.  Running one of those directly from a controller callback
blocks the PS4 reader thread for its whole duration, and because the kernel's
evdev ring buffer is small and fixed, everything the user presses meanwhile is
discarded outright.  Handing the action to this worker instead keeps the read
loop free.

Deliberately a plain list plus a lock rather than ``queue.Queue``: MicroPython
has no ``queue`` module, nor the condition variables it is built on, so the
worker polls.

The queue is bounded.  An unbounded one would let a burst of button presses
accumulate minutes of pending speech that plays back long after the user
stopped asking for it; dropping the newest submission keeps the robot's
responses tied to what is happening now.

Usage::

    worker = BackgroundWorker(name="actions")
    worker.start()
    worker.submit(ev3.speaker.say, "Hello")
    worker.stop()
"""

import threading
from time import sleep as _sleep

from threading_compat import create_lock, join_thread, thread_is_alive

DEFAULT_MAX_QUEUE = 4

# How often the worker wakes to look for new work.  Small enough that a
# button press feels immediate, large enough not to spin the CPU on a
# 300MHz ARM.
DEFAULT_POLL_INTERVAL_S = 0.02

# Poll interval once the queue has been empty for a while.  Every wake-up is
# a GIL handoff contended with the PS4 reader thread, and MicroPython holds
# the GIL across C calls, so an idle worker waking 50 times a second costs
# the reader for nothing.  Backing off only delays the *first* action of a
# burst; the queue is drained at the fast interval once work appears.
DEFAULT_IDLE_POLL_INTERVAL_S = 0.15

# Empty polls before backing off, so a burst of actions is not slowed by a
# back-off that engages between two closely spaced submissions.
IDLE_POLLS_BEFORE_BACKOFF = 10


class BackgroundWorker:
    """A single background thread that runs submitted callables in order.

    Parameters
    ----------
    name:
        Label used in log output.
    max_queue:
        Maximum number of pending actions.  Submissions beyond this are
        dropped and counted in :attr:`dropped_count`.
    poll_interval:
        Seconds between queue checks.
    logger:
        Output function for warnings (defaults to ``print``).
    """

    def __init__(
        self,
        name="worker",
        max_queue=DEFAULT_MAX_QUEUE,
        poll_interval=DEFAULT_POLL_INTERVAL_S,
        logger=None,
        idle_poll_interval=DEFAULT_IDLE_POLL_INTERVAL_S,
    ):
        self.name = name
        self.max_queue = max_queue
        self.poll_interval = poll_interval
        self.idle_poll_interval = idle_poll_interval
        self._logger = logger if logger is not None else print

        self._lock = create_lock()
        self._queue = []
        self._thread = None
        self._running = False
        self._dropped_count = 0

    def start(self):
        """Start the worker thread.  Idempotent."""
        if self._running:
            return
        self._running = True
        # Pybricks MicroPython's Thread() accepts only ``target`` - passing
        # ``daemon``/``name`` raises TypeError (PEN-188).
        self._thread = threading.Thread(target=self._run)
        self._thread.start()

    def stop(self, timeout=2.0):
        """Stop the worker, abandoning anything still queued.

        Pending actions are dropped rather than drained: this is called
        during shutdown, where finishing a queued 7-second announcement
        would delay stopping the motors.
        """
        self._running = False
        with self._lock:
            self._queue = []
        if thread_is_alive(self._thread):
            join_thread(self._thread, timeout=timeout)
        self._thread = None

    def submit(self, action, *args):
        """Queue *action* to run on the worker thread.

        Returns ``True`` if it was queued, ``False`` if it was dropped
        because the worker is stopped or the queue is full.  Never blocks
        and never raises, so a control-path caller cannot be stalled or
        broken by the queueing itself.
        """
        if not self._running:
            self._dropped_count += 1
            return False

        with self._lock:
            if len(self._queue) >= self.max_queue:
                self._dropped_count += 1
                dropped = True
            else:
                self._queue.append((action, args))
                dropped = False

        if dropped:
            try:
                self._logger(
                    "BackgroundWorker '{}': queue full, dropped an action"
                    " (total dropped: {})".format(self.name, self._dropped_count)
                )
            except Exception:  # noqa: BLE001 - logging must never break a caller
                pass
            return False
        return True

    def submit_or_run(self, action, *args):
        """Queue *action*, falling back to running it inline if the worker
        is not up (early startup, or after shutdown).

        A **full queue is not** such a fallback case, and the distinction
        matters: running inline there would put a multi-second action back
        on the caller's thread during exactly the burst of submissions the
        bounded queue exists to absorb -- for the PS4 reader thread, that is
        the dropped-input failure this worker was added to prevent.  A full
        queue drops, and :meth:`submit` has already logged it.

        Returns True if the action was queued rather than run inline.
        """
        if self._running:
            self.submit(action, *args)
            return True

        action(*args)
        return False

    def is_running(self):
        return self._running

    @property
    def pending(self):
        with self._lock:
            return len(self._queue)

    @property
    def dropped_count(self):
        return self._dropped_count

    def run_pending(self):
        """Run every currently-queued action.  Returns how many ran.

        Exposed separately from the thread loop so tests can drive the
        worker deterministically without timing races.
        """
        ran = 0
        while True:
            with self._lock:
                if not self._queue:
                    break
                action, args = self._queue.pop(0)

            ran += 1
            try:
                action(*args)
            except Exception as exc:  # noqa: BLE001
                # One failing action must not take down the worker thread and
                # silently disable every later action for the session.
                try:
                    self._logger(
                        "BackgroundWorker '{}': action raised {}: {}".format(
                            self.name, type(exc).__name__, exc
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass
        return ran

    def _run(self):
        empty_polls = 0
        while self._running:
            if self.run_pending() > 0:
                empty_polls = 0
                continue
            empty_polls += 1
            if empty_polls > IDLE_POLLS_BEFORE_BACKOFF:
                _sleep(self.idle_poll_interval)
            else:
                _sleep(self.poll_interval)
