"""
Telemetry event collector for the EV3 robot controller.

Responsible for:
- Building well-formed telemetry event envelopes from raw robot data.
- Buffering events in memory (up to ``max_buffer_size`` events).
- Optionally persisting overflow events to a local disk file so no data
  is lost when the send queue is full or the network is unavailable.

Designed to be MicroPython-compatible: no external library dependencies;
``uuid`` and ``datetime`` are used only when available and fall back to
simple integer-based IDs and epoch timestamps otherwise.

Usage::

    from telemetry.collector import TelemetryCollector

    collector = TelemetryCollector(source="ev3")
    collector.collect_battery_status(voltage_mv=7500, percentage=90.0)
    events = collector.flush()   # returns list of event dicts, clears buffer
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Optional standard-library imports (not available on MicroPython)
# ---------------------------------------------------------------------------

try:
    import uuid as _uuid_mod
    _HAS_UUID = True
except ImportError:
    _HAS_UUID = False

try:
    from datetime import datetime, timezone
    _HAS_DATETIME = True
except ImportError:
    _HAS_DATETIME = False

try:
    import time as _time
    _HAS_TIME = True
except ImportError:
    _HAS_TIME = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_BUFFER_SIZE = 500
DEFAULT_MAX_DISK_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_OVERFLOW_PATH = "/tmp/wrack_telemetry_overflow.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_counter = 0


def _generate_event_id() -> str:
    """Return a unique event ID string.

    Uses ``uuid.uuid4()`` when available; otherwise falls back to a simple
    monotonically increasing counter prefixed with zeros so downstream
    validators (which expect UUID format) can still be satisfied during tests
    that mock the ID.
    """
    if _HAS_UUID:
        return str(_uuid_mod.uuid4())
    global _counter
    _counter += 1
    # Produce a deterministic UUID-shaped string for MicroPython
    hex_str = format(_counter, "032x")
    return f"{hex_str[0:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}"


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string ending in ``Z``."""
    if _HAS_DATETIME:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if _HAS_TIME:
        try:
            epoch = int(_time.time())
            if hasattr(_time, "gmtime"):
                tm = _time.gmtime(epoch)
                return (
                    f"{tm[0]:04d}-{tm[1]:02d}-{tm[2]:02d}T"
                    f"{tm[3]:02d}:{tm[4]:02d}:{tm[5]:02d}Z"
                )
        except Exception:
            pass
    return "1970-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# TelemetryCollector
# ---------------------------------------------------------------------------


class TelemetryCollector:
    """Collect, buffer, and expose telemetry events from the EV3 controller.

    Parameters
    ----------
    source:
        The event source string (e.g. ``"ev3"``).  Must be one of the
        values defined in ``telemetry.schemas.VALID_SOURCES``.
    max_buffer_size:
        Maximum number of events to hold in memory before falling back to
        disk persistence.  Oldest events are dropped after the limit is
        reached *and* disk persistence is also full.
    overflow_path:
        File path used to persist overflow events to disk.  Set to
        ``None`` to disable disk persistence.
    max_disk_bytes:
        Maximum bytes written to the overflow file.  Writing stops once
        this limit is reached.
    """

    def __init__(
        self,
        source: str = "ev3",
        max_buffer_size: int = DEFAULT_MAX_BUFFER_SIZE,
        overflow_path: Optional[str] = DEFAULT_OVERFLOW_PATH,
        max_disk_bytes: int = DEFAULT_MAX_DISK_BYTES,
    ) -> None:
        self.source = source
        self.max_buffer_size = max_buffer_size
        self.overflow_path = overflow_path
        self.max_disk_bytes = max_disk_bytes

        self._buffer: List[Dict[str, Any]] = []
        self._dropped_count: int = 0

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
    ) -> Dict[str, Any]:
        """Build a fully-formed telemetry event envelope dict.

        Parameters
        ----------
        event_type:
            One of the recognised event type strings
            (e.g. ``"battery_status"``).
        payload:
            Event-type-specific payload dict.
        event_id:
            Override the auto-generated UUID (useful in tests).
        timestamp:
            Override the auto-generated timestamp (useful in tests).
        source:
            Override the collector's default source.

        Returns
        -------
        dict
            A dict conforming to the event envelope schema.
        """
        return {
            "event_id": event_id or _generate_event_id(),
            "event_type": event_type,
            "source": source or self.source,
            "timestamp": timestamp or _utc_now_iso(),
            "payload": payload,
        }

    # ------------------------------------------------------------------
    # collect helpers — one per P0 event type
    # ------------------------------------------------------------------

    def collect_battery_status(
        self,
        voltage_mv: int,
        percentage: float,
        *,
        voltage_v: Optional[float] = None,
        is_critical: Optional[bool] = None,
        battery_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create and buffer a ``battery_status`` event.

        Parameters
        ----------
        voltage_mv:
            Battery voltage in millivolts (non-negative integer).
        percentage:
            State of charge 0–100.
        voltage_v:
            Optional voltage in volts (float).
        is_critical:
            Optional flag indicating critically-low battery.
        battery_type:
            One of ``"rechargeable"``, ``"alkaline"``, or ``"unknown"``.
        """
        payload: Dict[str, Any] = {
            "voltage_mv": voltage_mv,
            "percentage": percentage,
        }
        if voltage_v is not None:
            payload["voltage_v"] = voltage_v
        if is_critical is not None:
            payload["is_critical"] = is_critical
        if battery_type is not None:
            payload["battery_type"] = battery_type

        event = self.create_event("battery_status", payload)
        self._buffer_event(event)
        return event

    def collect_command_received(
        self,
        command: str,
        *,
        controller_type: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create and buffer a ``command_received`` event."""
        payload: Dict[str, Any] = {"command": command}
        if controller_type is not None:
            payload["controller_type"] = controller_type
        if params is not None:
            payload["params"] = params

        event = self.create_event("command_received", payload)
        self._buffer_event(event)
        return event

    def collect_command_executed(
        self,
        command: str,
        success: bool,
        *,
        duration_ms: Optional[float] = None,
        controller_type: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create and buffer a ``command_executed`` event."""
        payload: Dict[str, Any] = {"command": command, "success": success}
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if controller_type is not None:
            payload["controller_type"] = controller_type
        if error_message is not None:
            payload["error_message"] = error_message

        event = self.create_event("command_executed", payload)
        self._buffer_event(event)
        return event

    def collect_device_status(
        self,
        device_name: str,
        status: str,
        *,
        device_type: Optional[str] = None,
        port: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create and buffer a ``device_status`` event."""
        payload: Dict[str, Any] = {
            "device_name": device_name,
            "status": status,
        }
        if device_type is not None:
            payload["device_type"] = device_type
        if port is not None:
            payload["port"] = port
        if error_message is not None:
            payload["error_message"] = error_message

        event = self.create_event("device_status", payload)
        self._buffer_event(event)
        return event

    def collect_error(
        self,
        error_type: str,
        message: str,
        *,
        stack_trace: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create and buffer an ``error`` event."""
        payload: Dict[str, Any] = {
            "error_type": error_type,
            "message": message,
        }
        if stack_trace is not None:
            payload["stack_trace"] = stack_trace
        if context is not None:
            payload["context"] = context

        event = self.create_event("error", payload)
        self._buffer_event(event)
        return event

    def collect_connection_status(
        self,
        connected: bool,
        *,
        host: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create and buffer a ``connection_status`` event."""
        payload: Dict[str, Any] = {"connected": connected}
        if host is not None:
            payload["host"] = host
        if error_message is not None:
            payload["error_message"] = error_message

        event = self.create_event("connection_status", payload)
        self._buffer_event(event)
        return event

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------

    def _buffer_event(self, event: Dict[str, Any]) -> None:
        """Append an event to the in-memory buffer.

        When the buffer is full the oldest event is removed.  If disk
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
            current_size = 0
            if os.path.exists(self.overflow_path):
                current_size = os.path.getsize(self.overflow_path)
            if current_size >= self.max_disk_bytes:
                self._dropped_count += 1
                return
            with open(self.overflow_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event) + "\n")
        except OSError:
            self._dropped_count += 1

    # ------------------------------------------------------------------
    # Public buffer accessors
    # ------------------------------------------------------------------

    def flush(self) -> List[Dict[str, Any]]:
        """Return all buffered events and clear the in-memory buffer.

        Returns
        -------
        list
            Copy of the current buffer; the internal buffer is emptied.
        """
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
        events: List[Dict[str, Any]] = []
        try:
            with open(self.overflow_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except (ValueError, KeyError):
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
