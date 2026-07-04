"""
Telemetry event collector for the Raspberry Pi vision/analytics module (PEN-166).

Standalone counterpart to ``robot/controller/telemetry/collector.py`` — this
runs on standard CPython (Raspberry Pi OS), so none of the MicroPython
compatibility guards used by the EV3 module are needed here.

Responsible for:
- Building well-formed telemetry event envelopes from Raspberry Pi data.
- Buffering events in memory (up to ``max_buffer_size`` events).
- Optionally persisting overflow events to a local disk file so no data
  is lost when the send queue is full or the network is unavailable.

Usage::

    from telemetry.collector import RpiTelemetryCollector

    collector = RpiTelemetryCollector()
    collector.collect("device_status", device_name="camera", status="connected")
    events = collector.flush()   # returns list of event dicts, clears buffer
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .schemas import ValidationError, validate_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_BUFFER_SIZE = 500
DEFAULT_MAX_DISK_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_OVERFLOW_PATH = "/tmp/wrack_rpi_telemetry_overflow.json"
DEFAULT_DEVICE_ID = "rpi-camera-01"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_event_id() -> str:
    """Return a unique event ID string (UUID v4)."""
    return str(uuid.uuid4())


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string ending in ``Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# RpiTelemetryCollector
# ---------------------------------------------------------------------------


class RpiTelemetryCollector:
    """Collect, buffer, and expose telemetry events from the Raspberry Pi.

    Parameters
    ----------
    source:
        The event source string. Defaults to ``"rpi"``.
    device_id:
        Identifier for this Raspberry Pi (e.g. ``"rpi-camera-01"``). Falls
        back to the ``RPI_DEVICE_ID`` environment variable, then
        :data:`DEFAULT_DEVICE_ID`.
    session_id:
        Optional session UUID to group related events (e.g. one process
        run). If *None*, a new UUID is generated at construction time.
    max_buffer_size:
        Maximum number of events to hold in memory before falling back to
        disk persistence. Oldest events are dropped after the limit is
        reached *and* disk persistence is also full.
    overflow_path:
        File path used to persist overflow events to disk. Set to ``None``
        to disable disk persistence.
    max_disk_bytes:
        Maximum bytes written to the overflow file. Writing stops once
        this limit is reached.
    validate:
        When ``True`` (default), events passed to :meth:`collect` /
        :meth:`collect_raw` are validated against ``telemetry.schemas``
        before buffering; invalid events are dropped and counted via
        :attr:`invalid_count`.
    """

    def __init__(
        self,
        source: str = "rpi",
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
        max_buffer_size: int = DEFAULT_MAX_BUFFER_SIZE,
        overflow_path: Optional[str] = DEFAULT_OVERFLOW_PATH,
        max_disk_bytes: int = DEFAULT_MAX_DISK_BYTES,
        validate: bool = True,
    ) -> None:
        self.source = source
        self.device_id = device_id or os.environ.get("RPI_DEVICE_ID", DEFAULT_DEVICE_ID)
        self.session_id = session_id or str(uuid.uuid4())
        self.max_buffer_size = max_buffer_size
        self.overflow_path = overflow_path
        self.max_disk_bytes = max_disk_bytes
        self.validate = validate

        self._buffer: List[Dict[str, Any]] = []
        self._dropped_count = 0
        self._invalid_count = 0

    # ------------------------------------------------------------------
    # Core factory method
    # ------------------------------------------------------------------

    def create_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        event_id: Optional[str] = None,
        timestamp: Optional[str] = None,
        source: Optional[str] = None,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a fully-formed telemetry event envelope dict."""
        return {
            "event_id": event_id or _generate_event_id(),
            "event_type": event_type,
            "source": source or self.source,
            "timestamp": timestamp or _utc_now_iso(),
            "device_id": device_id or self.device_id,
            "session_id": session_id or self.session_id,
            "payload": payload,
        }

    # ------------------------------------------------------------------
    # Generic collect API
    # ------------------------------------------------------------------

    def collect(self, event_type: str, **payload: Any) -> Optional[Dict[str, Any]]:
        """Build, validate, and buffer an event from a generic payload.

        Returns the buffered event dict on success; ``None`` if the event
        failed validation (and :attr:`invalid_count` is incremented).
        """
        event = self.create_event(event_type, dict(payload))
        return self.collect_raw(event)

    def collect_raw(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate and buffer a fully-formed event envelope.

        Intended for callers that build their own envelope (e.g.
        :func:`telemetry.builder.build_vision_detection_event`). Returns the
        event on success; ``None`` if it failed validation.
        """
        if self.validate:
            try:
                validate_event(event)
            except ValidationError:
                self._invalid_count += 1
                return None

        self._buffer_event(event)
        return event

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------

    def _buffer_event(self, event: Dict[str, Any]) -> None:
        """Append an event to the in-memory buffer.

        When the buffer is full the oldest event is removed. If disk
        persistence is enabled the removed event is written there instead.
        """
        if len(self._buffer) >= self.max_buffer_size:
            evicted = self._buffer.pop(0)
            self._persist_to_disk(evicted)
        self._buffer.append(event)

    def _persist_to_disk(self, event: Dict[str, Any]) -> None:
        """Append a single event to the overflow file (if enabled)."""
        if not self.overflow_path:
            self._dropped_count += 1
            return
        try:
            line = json.dumps(event) + "\n"
            line_bytes = len(line.encode("utf-8"))
            current_size = 0
            if os.path.exists(self.overflow_path):
                current_size = os.path.getsize(self.overflow_path)
            # Reject before writing so a single large event cannot push the
            # file past the configured cap.
            if current_size + line_bytes > self.max_disk_bytes:
                self._dropped_count += 1
                return
            with open(self.overflow_path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            self._dropped_count += 1

    # ------------------------------------------------------------------
    # Public buffer accessors
    # ------------------------------------------------------------------

    def flush(self) -> List[Dict[str, Any]]:
        """Return all buffered events and clear the in-memory buffer."""
        events = list(self._buffer)
        self._buffer.clear()
        return events

    def peek(self) -> List[Dict[str, Any]]:
        """Return a snapshot of the buffer without clearing it."""
        return list(self._buffer)

    @property
    def buffer_size(self) -> int:
        """Number of events currently in the in-memory buffer."""
        return len(self._buffer)

    @property
    def dropped_count(self) -> int:
        """Number of events dropped due to buffer + disk overflow."""
        return self._dropped_count

    @property
    def invalid_count(self) -> int:
        """Number of events rejected by :meth:`collect`/:meth:`collect_raw` due to validation failure."""
        return self._invalid_count

    def clear(self) -> None:
        """Discard all buffered events without sending them."""
        self._buffer.clear()

    def load_overflow(self) -> List[Dict[str, Any]]:
        """Read and return events from the overflow file (one JSON per line).

        The overflow file is *not* deleted by this method — call
        ``clear_overflow()`` once the events have been sent successfully.
        """
        if not self.overflow_path or not os.path.exists(self.overflow_path):
            return []
        events = []
        try:
            with open(self.overflow_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except ValueError:
                            pass
        except OSError:
            pass
        return events

    def clear_overflow(self) -> None:
        """Delete the overflow file if it exists."""
        if self.overflow_path and os.path.exists(self.overflow_path):
            try:
                os.remove(self.overflow_path)
            except OSError:
                pass
