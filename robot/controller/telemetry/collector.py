"""
TelemetryCollector — event buffering for the EV3 robot controller.

Buffers structured telemetry events in memory and provides thread-safe access
for background flush/send operations.  Designed for CPython (ev3dev Linux) and
falls back gracefully on MicroPython targets that lack ``threading``.

Usage::

    from telemetry.collector import TelemetryCollector

    collector = TelemetryCollector(device_id="ev3-001")
    collector.collect("battery_status", voltage_mv=7200, percentage=85)
    events = collector.flush()
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import threading as _threading
    _THREADING_AVAILABLE = True
except ImportError:  # MicroPython
    _THREADING_AVAILABLE = False


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string ending in Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _NoLock:
    """Drop-in lock replacement for single-threaded environments."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class TelemetryCollector:
    """Thread-safe, in-memory event buffer for EV3 telemetry.

    Parameters
    ----------
    max_buffer_size:
        Maximum number of events kept in memory.  When the buffer is full the
        *oldest* event is dropped (FIFO overflow policy).  Defaults to ``500``.
    device_id:
        Optional identifier for the hardware unit emitting events (e.g.
        ``"ev3-001"``).  Included in every event envelope.
    session_id:
        Optional session identifier.  A random UUID is generated if omitted.
    """

    def __init__(
        self,
        max_buffer_size: int = 500,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        self.max_buffer_size = max_buffer_size
        self.device_id = device_id
        self.session_id: str = session_id if session_id is not None else str(uuid.uuid4())

        self._buffer: List[Dict[str, Any]] = []
        self._lock = _threading.Lock() if _THREADING_AVAILABLE else _NoLock()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def collect(self, event_type: str, **payload: Any) -> Dict[str, Any]:
        """Build and buffer a telemetry event.

        Parameters
        ----------
        event_type:
            One of the recognised event type strings (e.g. ``"battery_status"``).
        **payload:
            Keyword arguments that become the event ``payload`` dict.

        Returns
        -------
        dict
            The complete event envelope that was buffered.
        """
        event: Dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "source": "ev3",
            "timestamp": _utc_now_iso(),
            "session_id": self.session_id,
            "payload": payload,
        }
        if self.device_id is not None:
            event["device_id"] = self.device_id

        with self._lock:
            if len(self._buffer) >= self.max_buffer_size:
                self._buffer.pop(0)
            self._buffer.append(event)

        return event

    def flush(self) -> List[Dict[str, Any]]:
        """Return all buffered events and clear the buffer.

        Returns
        -------
        list
            Snapshot of all events that were in the buffer.
        """
        with self._lock:
            events = list(self._buffer)
            self._buffer.clear()
        return events

    def peek(self) -> List[Dict[str, Any]]:
        """Return a copy of the buffer without clearing it."""
        with self._lock:
            return list(self._buffer)

    def size(self) -> int:
        """Return the current number of buffered events."""
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        """Discard all buffered events."""
        with self._lock:
            self._buffer.clear()
