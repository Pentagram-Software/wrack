"""
Wrack telemetry event collector for the EV3 robot controller.

This module provides :class:`TelemetryCollector`, a thread-safe, buffered
event collector that builds standard telemetry event envelopes and stores
them in an in-memory FIFO queue with optional disk spill on overflow.

Usage::

    from telemetry.collector import TelemetryCollector

    collector = TelemetryCollector(
        source="ev3",
        session_id="session-abc",
        device_id="ev3-unit-1",
        max_buffer=500,
        disk_spill_path="/tmp/telemetry_overflow.jsonl",
    )

    # Record a battery status event
    collector.collect("battery_status", voltage_mv=7200, percentage=85.0)

    # Retrieve and drain the buffer
    events = collector.flush()
"""

from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .schemas import ValidationError, validate_event

# ---------------------------------------------------------------------------
# Optional: UUID generation (uuid module; MicroPython has a minimal version)
# ---------------------------------------------------------------------------

try:
    import uuid as _uuid_mod

    def _new_uuid() -> str:
        return str(_uuid_mod.uuid4())

except ImportError:  # pragma: no cover — MicroPython fallback
    import random  # type: ignore[import]

    def _new_uuid() -> str:  # type: ignore[misc]
        hex_chars = "0123456789abcdef"
        parts = []
        for length in (8, 4, 4, 4, 12):
            parts.append("".join(random.choice(hex_chars) for _ in range(length)))
        return "-".join(parts)


# ---------------------------------------------------------------------------
# Optional: threading (not available on MicroPython)
# ---------------------------------------------------------------------------

try:
    from threading import Lock as _Lock

    def _make_lock():
        return _Lock()

except ImportError:  # pragma: no cover — MicroPython fallback
    class _NoOpLock:  # type: ignore[no-redef]
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    def _make_lock():  # type: ignore[misc]
        return _NoOpLock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string ending in Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# TelemetryCollector
# ---------------------------------------------------------------------------


class TelemetryCollector:
    """
    Buffered, thread-safe telemetry event collector.

    Builds standard event envelopes (UUID event_id, ISO timestamp, source,
    session/device IDs, JSON payload) and stores them in a bounded in-memory
    FIFO deque.  When the buffer is full the *oldest* event is dropped first
    (FIFO drop); if *disk_spill_path* is set the dropped event is written to
    that file as a JSON line before being removed from memory.

    Parameters
    ----------
    source:
        Event source tag (one of ``VALID_SOURCES`` — e.g. ``"ev3"``).
    session_id:
        Optional session identifier injected into every event envelope.
    device_id:
        Optional device identifier injected into every event envelope.
    max_buffer:
        Maximum number of events held in memory (default 500).
    disk_spill_path:
        Optional path to a file used for overflow events.  Each spilled event
        is appended as a single JSON line.  The file is created if it does not
        exist.  Pass ``None`` to disable disk spill (default).
    validate:
        If ``True`` (default) each event is validated via
        :func:`telemetry.schemas.validate_event` before being buffered.
        Invalid events are silently discarded; the validation error is
        available via the return value of :meth:`collect`.
    """

    def __init__(
        self,
        source: str = "ev3",
        session_id: Optional[str] = None,
        device_id: Optional[str] = None,
        max_buffer: int = 500,
        disk_spill_path: Optional[str] = None,
        validate: bool = True,
    ) -> None:
        self._source = source
        self._session_id = session_id
        self._device_id = device_id
        self._max_buffer = max_buffer
        self._disk_spill_path = disk_spill_path
        self._validate = validate

        self._buffer: deque = deque()
        self._lock = _make_lock()
        self._dropped_count: int = 0
        self._invalid_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect(
        self, event_type: str, **data: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Build and buffer a telemetry event.

        Parameters
        ----------
        event_type:
            One of ``VALID_EVENT_TYPES`` (e.g. ``"battery_status"``).
        **data:
            Payload fields for the event type.  These are passed verbatim as
            the ``payload`` dict.

        Returns
        -------
        dict or None
            The buffered event dict on success; ``None`` if the event failed
            validation.
        """
        event = self._build_event(event_type, data)

        if self._validate:
            try:
                validate_event(event)
            except ValidationError:
                with self._lock:
                    self._invalid_count += 1
                return None

        with self._lock:
            if len(self._buffer) >= self._max_buffer:
                dropped = self._buffer.popleft()
                self._dropped_count += 1
                self._spill_to_disk(dropped)
            self._buffer.append(event)

        return event

    def get_events(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Return a snapshot of buffered events without removing them.

        Parameters
        ----------
        limit:
            Maximum number of events to return.  ``None`` returns all.

        Returns
        -------
        list[dict]
            A copy of the buffered events (oldest first).
        """
        with self._lock:
            events = list(self._buffer)
        return events if limit is None else events[:limit]

    def flush(self) -> List[Dict[str, Any]]:
        """
        Return all buffered events and clear the buffer.

        Returns
        -------
        list[dict]
            All buffered events (oldest first).  The internal buffer is
            cleared after this call.
        """
        with self._lock:
            events = list(self._buffer)
            self._buffer.clear()
        return events

    def size(self) -> int:
        """Return the number of events currently in the buffer."""
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        """Discard all buffered events."""
        with self._lock:
            self._buffer.clear()

    @property
    def dropped_count(self) -> int:
        """Total number of events dropped due to buffer overflow."""
        with self._lock:
            return self._dropped_count

    @property
    def invalid_count(self) -> int:
        """Total number of events rejected due to validation failure."""
        with self._lock:
            return self._invalid_count

    @property
    def source(self) -> str:
        """The source tag used for all events from this collector."""
        return self._source

    @property
    def session_id(self) -> Optional[str]:
        """The session identifier injected into every event envelope."""
        return self._session_id

    @property
    def device_id(self) -> Optional[str]:
        """The device identifier injected into every event envelope."""
        return self._device_id

    @property
    def max_buffer(self) -> int:
        """The maximum number of events held in memory."""
        return self._max_buffer

    @property
    def disk_spill_path(self) -> Optional[str]:
        """The path used for overflow events, or ``None`` if disabled."""
        return self._disk_spill_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_event(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Construct a complete event envelope dict."""
        event: Dict[str, Any] = {
            "event_id": _new_uuid(),
            "event_type": event_type,
            "source": self._source,
            "timestamp": _utc_now_iso(),
            "payload": payload,
        }
        if self._session_id is not None:
            event["session_id"] = self._session_id
        if self._device_id is not None:
            event["device_id"] = self._device_id
        return event

    def _spill_to_disk(self, event: Dict[str, Any]) -> None:
        """Append a single event as a JSON line to the spill file."""
        if self._disk_spill_path is None:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._disk_spill_path)), exist_ok=True)
            with open(self._disk_spill_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event) + "\n")
        except (OSError, TypeError, ValueError):
            pass  # Best-effort — never raise from spill path (includes json serialization errors)
