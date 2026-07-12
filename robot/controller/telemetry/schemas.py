"""
Wrack telemetry event schemas and validation for the EV3 robot controller.

This module provides:

* String constants for all recognised event types and sources.
* ``validate_event(event)`` — validates the common envelope and the
  event-type-specific payload.  Raises ``ValidationError`` on failure.
* ``validate_payload(event_type, payload)`` — validates just the payload.

The canonical schema definitions live in
``shared/telemetry-types/schemas/*.json``; this module implements the same
constraints in pure Python so it runs on MicroPython without external libs.

When running in a standard CPython environment (e.g. during tests) the module
will optionally use ``jsonschema`` for full Draft-07 compliance.

Usage::

    from robot.controller.telemetry.schemas import validate_event, ValidationError

    try:
        validate_event(event_dict)
    except ValidationError as exc:
        print(exc.errors)
"""

import json
import os
import re

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
# Public constants
# ---------------------------------------------------------------------------

#: All recognised event sources.
VALID_SOURCES = ["ev3", "rpi", "cloud_functions", "web", "ios"]

#: All recognised event types.
VALID_EVENT_TYPES = [
    "battery_status",
    "command_received",
    "command_executed",
    "device_status",
    "error",
    "api_request",
    "motor_status",
    "sensor_reading",
    "terrain_scan",
    "connection_status",
    "video_stream_start",
    "video_stream_stop",
    "video_stream_health",
]

#: Coarse routing discriminator for the unified ingress (PEN-227): "health"
#: records route to Grafana Cloud, "event" records to BigQuery. Optional on
#: the envelope; absent records default to "event".
VALID_RECORD_TYPES = ["health", "event"]

#: P0-priority event types that have mandatory payload validation.
P0_EVENT_TYPES = [
    "battery_status",
    "command_received",
    "command_executed",
    "device_status",
    "error",
    "api_request",
    "video_stream_start",
    "video_stream_stop",
    "video_stream_health",
]

VALID_DEVICE_STATUSES = [
    "connected", "disconnected", "error", "stalled", "initializing"
]

VALID_DEVICE_TYPES = ["motor", "sensor", "controller", "unknown"]

VALID_BATTERY_TYPES = ["rechargeable", "alkaline", "unknown"]

VALID_CONTROLLER_TYPES = ["ps4", "ps5", "network_remote", "unknown"]

VALID_HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

# UUID v4 pattern
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# ISO 8601 UTC timestamp pattern (YYYY-MM-DDTHH:MM:SS[.fff]Z)
_ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)

# ---------------------------------------------------------------------------
# Optional jsonschema integration
# ---------------------------------------------------------------------------

try:
    import jsonschema  # type: ignore[import]
    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False


def _load_json_schema(schema_filename: str) -> Optional[Dict[str, Any]]:
    """Load a JSON Schema file from the shared schemas directory."""
    schemas_dir = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "shared", "telemetry-types", "schemas"
    )
    path = os.path.abspath(os.path.join(schemas_dir, schema_filename))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


_SCHEMA_FILENAME_MAP = {
    "battery_status": "battery_status.json",
    "command_received": "command_received.json",
    "command_executed": "command_executed.json",
    "device_status": "device_status.json",
    "error": "error.json",
    "api_request": "api_request.json",
    "video_stream_start": "video_stream_start.json",
    "video_stream_stop": "video_stream_stop.json",
    "video_stream_health": "video_stream_health.json",
}

# ---------------------------------------------------------------------------
# Validation error
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Raised when an event fails schema validation."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


# ---------------------------------------------------------------------------
# Envelope validation (pure Python, no external deps)
# ---------------------------------------------------------------------------

def _validate_envelope(event: Any) -> List[str]:
    """Return a list of error messages for the event envelope fields."""
    errors = []

    if not isinstance(event, dict):
        return ["event must be a dict (JSON object)"]

    # event_id
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not _UUID_RE.match(event_id):
        errors.append("event_id must be a valid UUID v4 string")

    # event_type
    event_type = event.get("event_type")
    if event_type not in VALID_EVENT_TYPES:
        errors.append(
            "event_type must be one of: " + ", ".join(VALID_EVENT_TYPES)
        )

    # source
    source = event.get("source")
    if source not in VALID_SOURCES:
        errors.append("source must be one of: " + ", ".join(VALID_SOURCES))

    # timestamp
    ts = event.get("timestamp")
    if not isinstance(ts, str) or not _ISO8601_RE.match(ts):
        errors.append(
            "timestamp must be an ISO 8601 UTC string ending in Z "
            "(e.g. 2026-01-01T00:00:00Z)"
        )

    # payload
    payload = event.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload must be a dict (JSON object)")

    # type (PEN-227) — optional, routes the event at the unified ingress.
    # VALID_RECORD_TYPES existed as a constant here without ever being
    # checked, so a typo like "heath" passed local validation and only
    # surfaced as a rejection once it reached the ingress — this mirrors
    # the check already present in the TypeScript validators
    # (shared/telemetry-types/typescript/events.ts,
    # cloud/functions/schemas.ts).
    record_type = event.get("type")
    if record_type is not None and record_type not in VALID_RECORD_TYPES:
        errors.append(
            "type must be one of: " + ", ".join(VALID_RECORD_TYPES) + " (or absent)"
        )

    return errors


# ---------------------------------------------------------------------------
# Payload validation (pure Python)
# ---------------------------------------------------------------------------

def _validate_battery_status_payload(payload: Any) -> List[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["battery_status payload must be a dict"]

    voltage_mv = payload.get("voltage_mv")
    if not isinstance(voltage_mv, int) or voltage_mv < 0:
        errors.append("payload.voltage_mv must be a non-negative integer")

    percentage = payload.get("percentage")
    if not isinstance(percentage, (int, float)) or not (0 <= percentage <= 100):
        errors.append("payload.percentage must be a number between 0 and 100")

    if "voltage_v" in payload and payload["voltage_v"] is not None:
        if not isinstance(payload["voltage_v"], (int, float)) or payload["voltage_v"] < 0:
            errors.append("payload.voltage_v must be a non-negative number")

    if "is_critical" in payload and payload["is_critical"] is not None:
        if not isinstance(payload["is_critical"], bool):
            errors.append("payload.is_critical must be a boolean")

    if "battery_type" in payload and payload["battery_type"] is not None:
        if payload["battery_type"] not in VALID_BATTERY_TYPES:
            errors.append(
                "payload.battery_type must be one of: " + ", ".join(VALID_BATTERY_TYPES)
            )

    return errors


def _validate_command_received_payload(payload: Any) -> List[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["command_received payload must be a dict"]

    command = payload.get("command")
    if not isinstance(command, str) or not command.strip():
        errors.append("payload.command must be a non-empty string")

        if "controller_type" in payload and payload["controller_type"] is not None:
            if payload["controller_type"] not in VALID_CONTROLLER_TYPES:
                errors.append(
                    "payload.controller_type must be one of: " + ", ".join(VALID_CONTROLLER_TYPES)
                )

    return errors


def _validate_command_executed_payload(payload: Any) -> List[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["command_executed payload must be a dict"]

    command = payload.get("command")
    if not isinstance(command, str) or not command.strip():
        errors.append("payload.command must be a non-empty string")

    success = payload.get("success")
    if not isinstance(success, bool):
        errors.append("payload.success must be a boolean")

    if "duration_ms" in payload and payload["duration_ms"] is not None:
        duration = payload["duration_ms"]
        if not isinstance(duration, (int, float)) or duration < 0:
            errors.append("payload.duration_ms must be a non-negative number")

    if "controller_type" in payload and payload["controller_type"] is not None:
        if payload["controller_type"] not in VALID_CONTROLLER_TYPES:
            errors.append(
                "payload.controller_type must be one of: " + ", ".join(VALID_CONTROLLER_TYPES)
            )

    return errors


def _validate_device_status_payload(payload: Any) -> List[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["device_status payload must be a dict"]

    device_name = payload.get("device_name")
    if not isinstance(device_name, str) or not device_name.strip():
        errors.append("payload.device_name must be a non-empty string")

    status = payload.get("status")
    if status not in VALID_DEVICE_STATUSES:
        errors.append(
            "payload.status must be one of: " + ", ".join(VALID_DEVICE_STATUSES)
        )

    if "device_type" in payload and payload["device_type"] is not None:
        if payload["device_type"] not in VALID_DEVICE_TYPES:
            errors.append(
                "payload.device_type must be one of: " + ", ".join(VALID_DEVICE_TYPES)
            )

    return errors


def _validate_error_payload(payload: Any) -> List[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["error payload must be a dict"]

    error_type = payload.get("error_type")
    if not isinstance(error_type, str) or not error_type.strip():
        errors.append("payload.error_type must be a non-empty string")

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        errors.append("payload.message must be a non-empty string")

    return errors


def _validate_api_request_payload(payload: Any) -> List[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["api_request payload must be a dict"]

    endpoint = payload.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        errors.append("payload.endpoint must be a non-empty string")

    status_code = payload.get("status_code")
    if not isinstance(status_code, int) or not (100 <= status_code <= 599):
        errors.append("payload.status_code must be an integer between 100 and 599")

    latency_ms = payload.get("latency_ms")
    if not isinstance(latency_ms, (int, float)) or latency_ms < 0:
        errors.append("payload.latency_ms must be a non-negative number")

    if "method" in payload and payload["method"] is not None:
        if payload["method"] not in VALID_HTTP_METHODS:
            errors.append(
                "payload.method must be one of: " + ", ".join(VALID_HTTP_METHODS)
            )

    return errors


VALID_STREAM_PROTOCOLS = ["udp", "tcp", "http"]


def _validate_video_stream_start_payload(payload: Any) -> List[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["video_stream_start payload must be a dict"]

    protocol = payload.get("protocol")
    if protocol not in VALID_STREAM_PROTOCOLS:
            errors.append(
                "payload.protocol must be one of: " + ", ".join(VALID_STREAM_PROTOCOLS)
            )

    port = payload.get("port")
    if not isinstance(port, int) or not (1 <= port <= 65535):
        errors.append("payload.port must be an integer between 1 and 65535")

    for dim in ("resolution_width", "resolution_height"):
        val = payload.get(dim)
        if not isinstance(val, int) or val < 1:
            errors.append("payload." + dim + " must be a positive integer")

    target_fps = payload.get("target_fps")
    if not isinstance(target_fps, (int, float)) or target_fps < 0:
        errors.append("payload.target_fps must be a non-negative number")

    return errors


def _validate_video_stream_stop_payload(payload: Any) -> List[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["video_stream_stop payload must be a dict"]

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append("payload.reason must be a non-empty string")

    if "uptime_seconds" in payload and payload["uptime_seconds"] is not None:
        uptime = payload["uptime_seconds"]
        if not isinstance(uptime, (int, float)) or uptime < 0:
            errors.append("payload.uptime_seconds must be a non-negative number")

    return errors


def _validate_video_stream_health_payload(payload: Any) -> List[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["video_stream_health payload must be a dict"]

    fps_recent = payload.get("fps_recent")
    if not isinstance(fps_recent, (int, float)) or fps_recent < 0:
        errors.append("payload.fps_recent must be a non-negative number")

    client_count = payload.get("client_count")
    if not isinstance(client_count, int) or client_count < 0:
        errors.append("payload.client_count must be a non-negative integer")

    frame_drop_total = payload.get("frame_drop_total")
    if not isinstance(frame_drop_total, int) or frame_drop_total < 0:
        errors.append("payload.frame_drop_total must be a non-negative integer")

    uptime_seconds = payload.get("uptime_seconds")
    if not isinstance(uptime_seconds, (int, float)) or uptime_seconds < 0:
        errors.append("payload.uptime_seconds must be a non-negative number")

    return errors


_PAYLOAD_VALIDATORS = {
    "battery_status": _validate_battery_status_payload,
    "command_received": _validate_command_received_payload,
    "command_executed": _validate_command_executed_payload,
    "device_status": _validate_device_status_payload,
    "error": _validate_error_payload,
    "api_request": _validate_api_request_payload,
    "video_stream_start": _validate_video_stream_start_payload,
    "video_stream_stop": _validate_video_stream_stop_payload,
    "video_stream_health": _validate_video_stream_health_payload,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_payload(event_type: str, payload: Any) -> None:
    """
    Validate the payload for a specific event type.

    Raises ``ValidationError`` if the payload is invalid.
    If ``jsonschema`` is installed the validation is additionally checked
    against the canonical JSON Schema file.
    """
    errors = []

    py_validator = _PAYLOAD_VALIDATORS.get(event_type)
    if py_validator:
        errors.extend(py_validator(payload))

    if errors:
        raise ValidationError(errors)

    # Optional: full JSON Schema validation (CPython dev/test environments)
    if _JSONSCHEMA_AVAILABLE:
        schema_file = _SCHEMA_FILENAME_MAP.get(event_type)
        if schema_file:
            schema = _load_json_schema(schema_file)
            if schema is not None:
                # Strip keys whose value is None before validating — JSON Schema
                # Draft-07 does not have a `nullable` keyword; optional fields
                # that are explicitly None are equivalent to being absent.
                clean_payload = {k: v for k, v in payload.items() if v is not None}
                try:
                    jsonschema.validate(instance=clean_payload, schema=schema)
                except jsonschema.ValidationError as exc:
                    raise ValidationError([exc.message]) from exc


def validate_event(event: Any) -> None:
    """
    Validate a complete telemetry event (envelope + payload).

    Raises ``ValidationError`` with a list of error messages if invalid.
    """
    envelope_errors = _validate_envelope(event)
    if envelope_errors:
        raise ValidationError(envelope_errors)

    event_type = event.get("event_type", "")
    payload = event.get("payload", {})
    validate_payload(event_type, payload)


def is_valid_event(event: Any) -> bool:
    """Return True if the event is valid, False otherwise (no exception)."""
    try:
        validate_event(event)
        return True
    except ValidationError:
        return False
