"""
HeartbeatSender — periodic EV3 liveness heartbeat over the unified ingress (PEN-229).

Sends a ``device_status`` event tagged ``type="health"`` on a fixed interval
so the unified ingress (PEN-227) routes it to the Grafana health leg. This is
the "currently-unscoped blocker" PEN-200 and PEN-203 both reference; interval
tuning (target: 5s interval / 15s offline threshold) is PEN-203's job, not
this one — :data:`DEFAULT_HEARTBEAT_INTERVAL` is a reasonable placeholder.

Usage::

    from telemetry.collector import TelemetryCollector
    from telemetry.sender import TelemetrySender
    from telemetry.heartbeat import HeartbeatSender

    collector = TelemetryCollector(source="ev3")
    sender = TelemetrySender(endpoint=..., device_id=..., device_token=...)
    heartbeat = HeartbeatSender(collector, sender)
    heartbeat.start()

    # … robot runs …

    heartbeat.stop()
"""

import time

# ``typing`` and ``from __future__ import annotations`` are unavailable on
# Pybricks/MicroPython.  Without the future import, function-signature
# annotations are evaluated at import time, so the fallback below provides a
# subscriptable stub (``Optional[str]`` etc. resolve to the stub harmlessly)
# that lets the module import on the EV3.
try:
    from typing import Any, Dict, Optional
except ImportError:  # pragma: no cover - MicroPython runtime path
    class _TypingStub:
        def __getitem__(self, item):
            return self

    Any = Dict = Optional = _TypingStub()  # type: ignore[assignment,misc]

try:
    import threading as _threading
    _THREADING_AVAILABLE = True
except ImportError:
    _threading = None  # type: ignore[assignment]
    _THREADING_AVAILABLE = False


# Placeholder default — PEN-203 owns tuning this to the real 5s/15s target.
DEFAULT_HEARTBEAT_INTERVAL = 30


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
        heartbeat immediately via ``send_events_async`` so a slow or failed
        send can never block the next tick.
    interval:
        Seconds between heartbeats. Defaults to
        :data:`DEFAULT_HEARTBEAT_INTERVAL`.
    """

    def __init__(
        self,
        collector: Any,
        sender: Any,
        interval: int = DEFAULT_HEARTBEAT_INTERVAL,
    ) -> None:
        if interval <= 0:
            raise ValueError("interval must be a positive integer")
        self.collector = collector
        self.sender = sender
        self.interval = interval

        self._running = False
        self._thread = None

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
            # ``join`` is unavailable on some Pybricks MicroPython builds; the
            # ``_running`` flag already tells the loop to exit, so treat join
            # as best-effort and fall back to a plain/absent join on the EV3.
            join = getattr(self._thread, "join", None)
            if callable(join):
                try:
                    join(timeout=timeout)
                except TypeError:
                    try:
                        join()
                    except Exception:
                        pass
                except Exception:
                    pass
            self._thread = None

    @property
    def is_running(self) -> bool:
        """``True`` while the periodic heartbeat thread is active."""
        return self._running

    # ------------------------------------------------------------------
    # Manual / forced send
    # ------------------------------------------------------------------

    def send_now(self) -> Optional[Dict[str, Any]]:
        """Build and send a single heartbeat immediately.

        Returns the event dict that was handed to the sender, or ``None`` if
        building the event failed.
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
        """Build and send one heartbeat event, isolating any failure.

        A bug building the event, or a send failure, must never kill the
        background loop — it should just skip this tick.
        """
        try:
            event = self.collector.create_heartbeat_event()
        except Exception as exc:  # noqa: BLE001 — one bad build must never kill the loop
            print("HeartbeatSender: failed to build heartbeat event: {}".format(exc))
            return None

        try:
            self.sender.send_events_async([event])
        except Exception as exc:  # noqa: BLE001 — one bad send must never kill the loop
            print("HeartbeatSender: send failed: {}".format(exc))

        return event
