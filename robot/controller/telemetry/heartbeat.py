"""
HeartbeatSender — periodic EV3 liveness heartbeat over the unified ingress (PEN-229).

Sends a ``device_status`` event tagged ``type="health"`` on a fixed interval
so the unified ingress (PEN-227) routes it to the Grafana health leg. This is
the "currently-unscoped blocker" PEN-200 and PEN-203 both reference; interval
tuning (target: 5s interval / 15s offline threshold) is PEN-203's job, not
this one — :data:`DEFAULT_HEARTBEAT_INTERVAL` is a reasonable placeholder.

As of PEN-234, the same heartbeat payload also carries battery state
(voltage/percentage/etc., merged onto the ``device_status`` payload) when a
``battery_info_provider`` callable is supplied — still one event, one bounded
HTTP POST per tick, rather than a second sender.

Usage::

    from telemetry.collector import TelemetryCollector
    from telemetry.sender import TelemetrySender
    from telemetry.heartbeat import HeartbeatSender

    collector = TelemetryCollector(source="ev3")
    sender = TelemetrySender(endpoint=..., device_id=..., device_token=...)
    heartbeat = HeartbeatSender(
        collector, sender,
        battery_info_provider=lambda: device_manager.get_battery_info(),
    )
    heartbeat.start()

    # … robot runs …

    heartbeat.stop()
"""

import time

from threading_compat import create_lock

# ``typing`` and ``from __future__ import annotations`` are unavailable on
# Pybricks/MicroPython.  Without the future import, function-signature
# annotations are evaluated at import time, so the fallback below provides a
# subscriptable stub (``Optional[str]`` etc. resolve to the stub harmlessly)
# that lets the module import on the EV3.
try:
    from typing import Any, Callable, Dict, Optional
except ImportError:  # pragma: no cover - MicroPython runtime path
    class _TypingStub:
        def __getitem__(self, item):
            return self

    Any = Callable = Dict = Optional = _TypingStub()  # type: ignore[assignment,misc]

try:
    import threading as _threading
    _THREADING_AVAILABLE = True
except ImportError:
    _threading = None  # type: ignore[assignment]
    _THREADING_AVAILABLE = False


# Placeholder default — PEN-203 owns tuning this to the real 5s/15s target.
DEFAULT_HEARTBEAT_INTERVAL = 30

# Heartbeats should use a TelemetrySender configured with these rather than
# TelemetrySender's own analytics-oriented defaults (10s timeout, 3 retries
# with backoff — up to ~47s worst case per send). A heartbeat is disposable:
# the next tick, DEFAULT_HEARTBEAT_INTERVAL seconds away, is just as good as
# a slow/failed one, so retrying only prolongs how long the tracked send
# thread can block for zero benefit. This bounds the worst case on any
# runtime where ``urequests.post()`` actually honors ``timeout`` — it cannot
# help on a build where ``urequests`` doesn't accept ``timeout`` at all (see
# the ``sender`` param docstring below): a single hung syscall can still
# block that one worker thread for the life of the program, since Pybricks
# MicroPython's Thread() has no daemon flag (PEN-188) and Python has no way
# to force-cancel a blocked socket call. What tracking in-flight sends does
# guarantee is that this is bounded to *at most one* such thread ever, not
# an unbounded, accumulating leak (code review).
DEFAULT_HEARTBEAT_SEND_TIMEOUT_S = 5
DEFAULT_HEARTBEAT_SEND_MAX_RETRIES = 0


class HeartbeatSender:
    """Periodically sends a ``type="health"`` liveness event to the ingress.

    Parameters
    ----------
    collector:
        A :class:`~telemetry.collector.TelemetryCollector`, used only to
        build well-formed event envelopes (:meth:`create_heartbeat_event`).
        Heartbeats are never buffered through the collector's normal
        analytics path — they are time-sensitive and must be sent
        immediately, not queued for the next flush.
    sender:
        A :class:`~telemetry.sender.TelemetrySender` used to POST each
        heartbeat. Sends run on a single dedicated worker thread that this
        class owns and tracks (see :meth:`_send_heartbeat`) — never via
        ``TelemetrySender.send_events_async``, which spawns an untracked
        thread per call and would accumulate one every tick for as long as
        a send stays hung (``urequests`` doesn't support a ``timeout``, so a
        network outage can block a send indefinitely — PEN-229 code review).
        Should be a *dedicated* ``TelemetrySender`` instance configured with
        :data:`DEFAULT_HEARTBEAT_SEND_TIMEOUT_S` /
        :data:`DEFAULT_HEARTBEAT_SEND_MAX_RETRIES` (see their docstring),
        not the shared analytics sender — its default 10s-timeout/3-retry
        behavior can block a single heartbeat send for up to ~47s for no
        benefit.
    interval:
        Seconds between heartbeats. Defaults to
        :data:`DEFAULT_HEARTBEAT_INTERVAL`.
    battery_info_provider:
        Optional zero-argument callable returning a raw battery-info dict
        (same shape as ``ev3_devices.DeviceManager.get_battery_info()``),
        called once per tick to merge battery fields into the heartbeat
        payload (PEN-234). Kept as an injected callable, not a direct
        ``DeviceManager`` reference, so ``telemetry/`` stays decoupled from
        ``ev3_devices`` — consistent with ``collector``/``sender`` already
        being injected rather than constructed internally. Omitting it (the
        default, ``None``) preserves today's liveness-only heartbeat
        unchanged. A failing or raising provider never blocks or skips the
        heartbeat itself — see :meth:`_send_heartbeat`.
    """

    def __init__(
        self,
        collector: Any,
        sender: Any,
        interval: int = DEFAULT_HEARTBEAT_INTERVAL,
        battery_info_provider: Optional[Callable[[], Any]] = None,
    ) -> None:
        if interval <= 0:
            raise ValueError("interval must be a positive integer")
        self.collector = collector
        self.sender = sender
        self.interval = interval
        self.battery_info_provider = battery_info_provider

        self._running = False
        self._thread = None
        # Tracks the single in-flight send worker thread (None when idle).
        # Bounds concurrent sends to at most one, regardless of how long a
        # send takes — see the ``sender`` param docstring above.
        #
        # ``_send_lock`` protects the check-then-set in ``_send_heartbeat``:
        # without it, a periodic tick and a concurrent ``send_now()`` call
        # can both observe ``_send_thread is None`` and both launch a worker,
        # defeating the one-worker bound (code review). Pybricks MicroPython
        # has no ``threading.Lock`` (see ``threading_compat``), hence
        # ``create_lock()`` rather than constructing one directly.
        #
        # ``_send_generation`` protects the clear in ``_send_worker``: a
        # worker only clears ``_send_thread`` if its generation still matches
        # the current one, so a worker can never clear a *different*,
        # possibly still-running worker's marker (code review).
        self._send_thread = None
        self._send_lock = create_lock()
        self._send_generation = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the periodic heartbeat loop.

        Safe to call multiple times — subsequent calls are no-ops if already
        running.
        """
        if self._running:
            return

        self._running = True

        if _THREADING_AVAILABLE:
            # Pybricks MicroPython's Thread() accepts only ``target`` —
            # passing ``daemon`` or ``name`` raises TypeError (PEN-188).  The
            # loop exits on the ``_running`` flag, so a daemon thread is
            # unnecessary.
            self._thread = _threading.Thread(target=self._run)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the periodic heartbeat loop.

        Parameters
        ----------
        timeout:
            Seconds to wait for the background thread to finish.
        """
        self._running = False
        if self._thread is not None and _THREADING_AVAILABLE:
            self._join_thread(self._thread, timeout)
            self._thread = None
        # Best-effort: wait briefly for an in-flight send too, so a caller
        # that stops right after a tick doesn't race a still-running worker.
        # If it's genuinely hung (the scenario this tracking exists for), the
        # join simply times out here and the thread is left to finish or die
        # on its own — never blocks stop() indefinitely.
        if self._send_thread is not None and _THREADING_AVAILABLE:
            self._join_thread(self._send_thread, timeout)

    @property
    def is_running(self) -> bool:
        """``True`` while the periodic heartbeat thread is active."""
        return self._running

    @staticmethod
    def _join_thread(thread: Any, timeout: float) -> None:
        """Best-effort wait for *thread* to finish, bounded by *timeout*.

        Tries ``join(timeout=...)`` first. Some Pybricks MicroPython builds
        don't accept the ``timeout`` kwarg on ``join()`` — falling back to a
        bare, unbounded ``join()`` there (as an earlier version of this
        method did) can block forever on ``_send_thread``, whose target
        performs unbounded network I/O (see ``_send_worker``), defeating
        ``stop(timeout)``'s whole contract (code review). Poll ``is_alive()``
        instead in short increments, so the wait is bounded by *timeout* on
        every runtime, with or without a ``timeout``-aware ``join()``.
        """
        join = getattr(thread, "join", None)
        if callable(join):
            try:
                join(timeout=timeout)
                return
            except TypeError:
                pass
            except Exception:
                return

        is_alive = getattr(thread, "is_alive", None)
        if not callable(is_alive):
            return

        poll_interval = 0.1
        waited = 0.0
        while waited < timeout:
            try:
                if not is_alive():
                    return
            except Exception:
                return
            time.sleep(poll_interval)
            waited += poll_interval

    # ------------------------------------------------------------------
    # Manual / forced send
    # ------------------------------------------------------------------

    def send_now(self) -> Optional[Dict[str, Any]]:
        """Build and send a single heartbeat immediately.

        Returns the event dict that was handed to the sender, or ``None`` if
        building the event failed, or if a previous heartbeat send is still
        in flight (see :meth:`_send_heartbeat`).
        """
        return self._send_heartbeat()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main loop — runs in a daemon thread.

        Ticks every second (like ``StatusCollector._run``) rather than
        sleeping for the whole interval, so :meth:`stop` remains responsive
        instead of blocking for up to ``interval`` seconds.
        """
        last = -self.interval  # fire immediately on the first tick

        while self._running:
            now = time.time()

            if now - last >= self.interval:
                self._send_heartbeat()
                last = now

            time.sleep(1)

    def _send_heartbeat(self) -> Optional[Dict[str, Any]]:
        """Build one heartbeat event and hand it to the send worker.

        Skips the tick entirely (does not build or send) while a previous
        send is still in flight, rather than spawning another thread on top
        of it — an outage that hangs one send must not accumulate a new
        thread every tick (PEN-229 code review: unbounded thread growth,
        since ``urequests`` has no ``timeout`` support and a hung request
        can block indefinitely). A bug building the event, or a send
        failure, must never kill the background loop — it should just skip
        this tick.

        The check, event build, and (when threading is available) thread
        launch all happen under ``_send_lock`` — without it, the periodic
        tick and a concurrent ``send_now()`` call could both observe
        ``_send_thread is None`` and both launch a worker, breaking the
        one-worker guarantee (code review). The lock is held only long
        enough to start the worker thread, never for the blocking send
        itself (that happens in ``_send_worker``, after ``Thread.start()``
        has already returned).

        When threading isn't available, ``_send_worker`` runs synchronously
        on this same thread instead — deliberately *outside* the ``with``
        block below, since ``_send_worker``'s own ``finally`` re-acquires
        ``_send_lock`` to clear the marker, and re-entering a non-reentrant
        lock from the thread that already holds it would deadlock.
        """
        run_synchronously = False

        with self._send_lock:
            if self._send_thread is not None:
                print("HeartbeatSender: skipping tick — previous send still in flight")
                return None

            battery_info = self._read_battery_info()

            try:
                event = self.collector.create_heartbeat_event(battery_info=battery_info)
            except Exception as exc:  # noqa: BLE001 — one bad build must never kill the loop
                print("HeartbeatSender: failed to build heartbeat event: {}".format(exc))
                return None

            self._send_generation += 1
            generation = self._send_generation

            if _THREADING_AVAILABLE:
                # Pybricks MicroPython's Thread() accepts only
                # ``target``/``args`` — passing ``daemon``/``name`` raises
                # TypeError (PEN-188).
                self._send_thread = _threading.Thread(
                    target=self._send_worker, args=(event, generation)
                )
                self._send_thread.start()
            else:
                run_synchronously = True

        if run_synchronously:
            # No threads on this runtime — send synchronously (outside the
            # lock, see docstring) so the event is never silently dropped,
            # mirroring TelemetrySender's own fallback behavior.
            self._send_worker(event, generation)

        return event

    def _read_battery_info(self) -> Optional[Any]:
        """Call :attr:`battery_info_provider`, if set, isolating exceptions.

        A battery read failing (e.g. a hardware glitch, or the EV3Brick
        reporting an error) must never prevent the liveness signal itself
        from being sent (PEN-234) — this returns ``None`` on any error, so
        :meth:`create_heartbeat_event` simply omits battery fields for that
        tick rather than skipping the heartbeat.
        """
        if self.battery_info_provider is None:
            return None
        try:
            return self.battery_info_provider()
        except Exception as exc:  # noqa: BLE001 — a bad battery read must never skip the heartbeat
            print("HeartbeatSender: battery_info_provider failed: {}".format(exc))
            return None

    def _send_worker(self, event: Dict[str, Any], generation: int) -> None:
        """Thread target: perform one blocking send, then clear the in-flight marker.

        Uses ``TelemetrySender.send_events`` (blocking) rather than
        ``send_events_async`` — this class already runs the send on its own
        tracked thread, so a second, untracked thread from the sender would
        defeat the whole point of tracking one in-flight send at a time.

        *generation* identifies which call to :meth:`_send_heartbeat`
        launched this worker. The marker is only cleared if it still matches
        the current generation — a worker must never clear a *different*
        (newer) worker's in-flight marker, which would let further sends
        proceed while this generation's own send remains unresolved (code
        review).
        """
        try:
            self.sender.send_events([event])
        except Exception as exc:  # noqa: BLE001 — one bad send must never kill the loop
            print("HeartbeatSender: send failed: {}".format(exc))
        finally:
            with self._send_lock:
                if generation == self._send_generation:
                    self._send_thread = None
