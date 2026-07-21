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

import json
import os

# ``typing`` and ``from __future__ import annotations`` are unavailable on
# Pybricks/MicroPython.  Without the future import, function-signature
# annotations are evaluated at import time, so the fallback below provides a
# subscriptable stub (``Optional[str]`` etc. resolve to the stub harmlessly)
# that lets the module import on the EV3.
try:
    from typing import Any, Dict, List, Optional
except ImportError:  # pragma: no cover - MicroPython runtime path
    class _TypingStub:
        def __getitem__(self, item):
            return self

    Any = Dict = List = Optional = _TypingStub()  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Optional standard-library imports (not available on MicroPython)
# ---------------------------------------------------------------------------

try:
    import uuid as _uuid_mod
    _HAS_UUID = hasattr(_uuid_mod, "uuid4")
except ImportError:
    _HAS_UUID = False

# Some MicroPython builds ship a partial ``datetime`` whose import raises
# ``AttributeError`` (e.g. "type object 'tzinfo' has no attribute '__new__'")
# rather than ``ImportError``; catch broadly so the module still loads and
# falls back to the ``time``-based timestamp path on the EV3.
try:
    from datetime import datetime, timezone
    _HAS_DATETIME = True
except Exception:  # pragma: no cover - MicroPython partial-datetime path
    _HAS_DATETIME = False

try:
    import time as _time
    _HAS_TIME = True
except ImportError:
    _HAS_TIME = False

# Schema validation is optional so the collector still imports on MicroPython
# (or any environment where ``telemetry.schemas`` cannot be loaded).  When it
# is unavailable the generic :meth:`TelemetryCollector.collect` simply skips
# validation regardless of the ``validate`` flag.  Also catches
# ``AttributeError``, not just ``ImportError``: ``schemas`` imports ``re`` and
# builds regexes at module scope, and some MicroPython builds ship partial
# standard-library modules that raise ``AttributeError`` rather than
# ``ImportError`` (see the ``datetime`` guard above). Deliberately narrow
# (not a bare ``except Exception``) so a real bug in ``schemas.py`` (e.g. a
# ``NameError`` from a typo) still fails loudly instead of silently disabling
# validation.
try:
    from .schemas import ValidationError, validate_event
    _HAS_SCHEMAS = True
except (ImportError, AttributeError):  # pragma: no cover - MicroPython / missing-schema / partial-module path
    _HAS_SCHEMAS = False

    class ValidationError(Exception):  # type: ignore[no-redef]
        """Fallback used when ``telemetry.schemas`` is unavailable."""

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


def _open_text(path: str, mode: str):
    """Open *path* as a UTF-8 text file, tolerant of MicroPython.

    CPython accepts an ``encoding`` keyword; Pybricks/MicroPython's ``open()``
    does not and raises ``TypeError``.  Fall back to a plain ``open()`` in that
    case so the overflow-persistence path works on the EV3.
    """
    try:
        return open(path, mode, encoding="utf-8")
    except TypeError:  # pragma: no cover - MicroPython runtime path
        return open(path, mode)


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
    # Produce a deterministic UUID-shaped string for MicroPython. Uses ``%``
    # formatting rather than the ``format()`` builtin, which some MicroPython
    # builds omit entirely.
    hex_str = "%032x" % _counter
    return "{}-{}-{}-{}-{}".format(hex_str[0:8], hex_str[8:12], hex_str[12:16], hex_str[16:20], hex_str[20:32])


#: Battery fields recognised by the ``battery_status`` payload schema
#: (``telemetry.schemas._validate_battery_status_payload``) that
#: :func:`_extract_battery_fields` will carry over onto a heartbeat's
#: ``device_status`` payload when present.
_OPTIONAL_BATTERY_FIELDS = ("voltage_v", "is_critical", "battery_type")


def _extract_battery_fields(info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return usable battery fields from a raw ``get_battery_info()``-shaped
    dict, or ``None`` if *info* is absent, unavailable, or missing the
    required fields (PEN-234).

    Mirrors ``StatusCollector._collect_battery_status``'s own
    availability/required-field checks so a heartbeat's battery data uses
    the same criteria as the (disabled-by-default) analytics battery event.
    Deliberately tolerant of a malformed *info* (e.g. not a dict) — this is
    called from the heartbeat's best-effort path, where a battery-data
    problem must never raise and block the liveness signal itself.
    """
    if not isinstance(info, dict):
        return None
    if not info.get("available", True):
        return None

    voltage_mv = info.get("voltage_mv")
    percentage = info.get("percentage")
    if voltage_mv is None or percentage is None:
        return None

    fields = {"voltage_mv": voltage_mv, "percentage": percentage}
    for key in _OPTIONAL_BATTERY_FIELDS:
        if info.get(key) is not None:
            fields[key] = info[key]
    return fields


#: Maps a DeviceManager motor device key to the heartbeat payload field name
#: it merges onto (PEN-200). Order also drives the ``payload`` key order in
#: :func:`_extract_motor_fields`.
_MOTOR_FIELD_MAP = (
    ("drive_L_motor", "motor_l_available"),
    ("drive_R_motor", "motor_r_available"),
    ("turret_motor", "turret_available"),
)


def _extract_motor_fields(motor_status: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return motor-availability payload fields from a raw motor-status dict.

    *motor_status* is expected in the shape of
    :meth:`~ev3_devices.DeviceManager.get_motor_availability` (PEN-200):
    ``{"drive_L_motor": bool, "drive_R_motor": bool, "turret_motor": bool}``.
    Only recognised keys with an actual ``bool`` value are carried over —
    missing keys are simply omitted (no ``None`` placeholders), and a
    malformed *motor_status* (not a dict, or non-bool values) never raises,
    mirroring :func:`_extract_battery_fields`'s tolerance: a motor-status
    read problem must never block or delay the heartbeat's liveness signal.
    """
    if not isinstance(motor_status, dict):
        return None

    fields = {}
    for device_key, field_name in _MOTOR_FIELD_MAP:
        value = motor_status.get(device_key)
        if isinstance(value, bool):
            fields[field_name] = value
    return fields or None


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
                    "%04d-%02d-%02dT%02d:%02d:%02dZ" % (
                        tm[0], tm[1], tm[2], tm[3], tm[4], tm[5]
                    )
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
    validate:
        When ``True`` (default), events passed to the generic :meth:`collect`
        method are validated against ``telemetry.schemas`` before buffering;
        invalid events are dropped and counted via :attr:`invalid_count`.
        Has no effect on the typed ``collect_*`` helpers.
    """

    def __init__(
        self,
        source: str = "ev3",
        max_buffer_size: int = DEFAULT_MAX_BUFFER_SIZE,
        overflow_path: Optional[str] = DEFAULT_OVERFLOW_PATH,
        max_disk_bytes: int = DEFAULT_MAX_DISK_BYTES,
        validate: bool = True,
    ) -> None:
        self.source = source
        self.max_buffer_size = max_buffer_size
        self.overflow_path = overflow_path
        self.max_disk_bytes = max_disk_bytes
        self.validate = validate

        self._buffer = []
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
        record_type: Optional[str] = None,
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
        record_type:
            Optional coarse routing discriminator for the unified ingress
            (PEN-227): ``"health"`` or ``"event"``. Omitted from the envelope
            when ``None`` (the ingress then defaults to ``"event"``), rather
            than being sent as an explicit ``None``.

        Returns
        -------
        dict
            A dict conforming to the event envelope schema.
        """
        event = {
            "event_id": event_id or _generate_event_id(),
            "event_type": event_type,
            "source": source or self.source,
            "timestamp": timestamp or _utc_now_iso(),
            "payload": payload,
        }
        if record_type is not None:
            event["type"] = record_type
        return event

    def create_heartbeat_event(
        self,
        *,
        device_name: str = "ev3",
        status: str = "connected",
        battery_info: Optional[Dict[str, Any]] = None,
        motor_status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build (but do not buffer) a liveness heartbeat event (PEN-229).

        Reuses the existing ``device_status`` event type rather than
        introducing a new one, so the unified ingress and shared schemas
        need no changes — tagged ``type="health"`` so the ingress (PEN-227)
        routes it to the Grafana health leg instead of BigQuery.

        Deliberately not buffered/returned via ``collect_device_status``:
        a heartbeat is time-sensitive and must be sent immediately by the
        caller, not queued for the next analytics flush (which could be
        minutes away).

        Parameters
        ----------
        battery_info:
            Optional raw battery-info dict, in the same shape as
            :class:`~ev3_devices.DeviceManager.get_battery_info` (PEN-234):
            ``voltage_mv``, ``percentage``, optionally ``voltage_v``,
            ``is_critical``, ``battery_type``, and ``available``. When
            present and usable, its fields are merged into this heartbeat's
            payload as recognised, optional ``device_status`` fields — the
            shared schema contract (``shared/telemetry-types/schemas/
            device_status.json``, its TypeScript/Python counterparts, and
            this module's own ``telemetry.schemas._validate_device_status_
            payload``) was updated to declare them explicitly, rather than
            relying on unrecognised-field leniency. Battery data is
            best-effort — a missing, unavailable, or malformed
            ``battery_info`` merges nothing rather than failing the
            heartbeat, since liveness must never be blocked by a battery
            read failure.
        motor_status:
            Optional raw motor-availability dict, in the same shape as
            :meth:`~ev3_devices.DeviceManager.get_motor_availability`
            (PEN-200): ``{"drive_L_motor": bool, "drive_R_motor": bool,
            "turret_motor": bool}``. When present, recognised keys are
            merged into this heartbeat's payload as ``motor_l_available``,
            ``motor_r_available``, and ``turret_available`` — the shared
            schema contract (``shared/telemetry-types/schemas/
            device_status.json``, its TypeScript/Python counterparts, and
            this module's own ``telemetry.schemas._validate_device_status_
            payload``) was updated to declare them explicitly. Best-effort,
            like ``battery_info``: a missing or malformed ``motor_status``
            merges nothing rather than failing the heartbeat.
        """
        payload = {"device_name": device_name, "status": status}
        battery_fields = _extract_battery_fields(battery_info)
        if battery_fields:
            payload.update(battery_fields)
        motor_fields = _extract_motor_fields(motor_status)
        if motor_fields:
            payload.update(motor_fields)
        return self.create_event("device_status", payload, record_type="health")

    # ------------------------------------------------------------------
    # Generic collect API
    # ------------------------------------------------------------------

    def collect(self, event_type: str, **payload: Any) -> Optional[Dict[str, Any]]:
        """Build, validate, and buffer an event from a generic payload.

        This is a schema-agnostic alternative to the typed ``collect_*``
        helpers: any ``event_type`` and arbitrary payload keyword arguments are
        accepted.  When the collector was constructed with ``validate=True``
        (the default) and ``telemetry.schemas`` is importable, the event is
        validated before buffering; events that fail validation are discarded,
        :attr:`invalid_count` is incremented, and ``None`` is returned.

        Parameters
        ----------
        event_type:
            One of the recognised event type strings (e.g. ``"battery_status"``).
        **payload:
            Event-type-specific payload fields, passed verbatim as the
            event ``payload`` dict.

        Returns
        -------
        dict or None
            The buffered event dict on success; ``None`` if the event failed
            validation.
        """
        event = self.create_event(event_type, dict(payload))

        if self.validate and _HAS_SCHEMAS:
            try:
                validate_event(event)
            except ValidationError:
                self._invalid_count += 1
                return None

        self._buffer_event(event)
        return event

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
        payload = {
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
        payload = {"command": command}
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
        payload = {"command": command, "success": success}
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
        payload = {
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
        payload = {
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
        payload = {"connected": connected}
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
            line = json.dumps(event) + "\n"
            try:
                line_bytes = len(line.encode("utf-8"))
            except Exception:  # noqa: BLE001 — fall back to char count
                line_bytes = len(line)
            current_size = 0
            if os.path.exists(self.overflow_path):
                current_size = os.path.getsize(self.overflow_path)
            # Reject before writing so a single large event cannot push the
            # file past the configured cap.
            if current_size + line_bytes > self.max_disk_bytes:
                self._dropped_count += 1
                return
            with _open_text(self.overflow_path, "a") as fh:
                fh.write(line)
        except Exception:  # noqa: BLE001 — best-effort overflow must never crash collect_*()
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

    @property
    def invalid_count(self) -> int:
        """Number of events rejected by :meth:`collect` due to validation failure."""
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
            with _open_text(self.overflow_path, "r") as fh:
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
