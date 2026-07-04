"""
Wrack Raspberry Pi telemetry event schemas and validation (PEN-166).

Standalone counterpart to ``robot/controller/telemetry/schemas.py`` for the
Raspberry Pi vision/analytics runtime. Runs on standard CPython, so none of
the MicroPython compatibility guards used by the EV3 module are needed here.

This module provides:

* String constants for all recognised RPi event types and sources.
* ``validate_event(event)`` — validates the common envelope and the
  event-type-specific payload. Raises ``ValidationError`` on failure.
* ``validate_payload(event_type, payload)`` — validates just the payload.

Usage::

    from telemetry.schemas import validate_event, ValidationError

    try:
        validate_event(event_dict)
    except ValidationError as exc:
        print(exc.errors)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Event sources this module produces. (The wider system also recognises
#: ``ev3``, ``cloud_functions``, ``web``, ``ios`` — this module is scoped to
#: the Raspberry Pi, so only ``rpi`` is accepted here.)
VALID_SOURCES = ["rpi"]

#: All recognised event types for the Raspberry Pi.
VALID_EVENT_TYPES = [
    "video_stream_start",
    "video_stream_stop",
    "video_stream_health",
    "device_status",
    "connection_status",
    "error",
    "vision_detection",
]

VALID_DEVICE_STATUSES = [
    "connected", "disconnected", "error", "stalled", "initializing"
]

VALID_DEVICE_TYPES = ["motor", "sensor", "controller", "camera", "unknown"]

VALID_STREAM_PROTOCOLS = ["udp", "tcp", "http"]

#: PEN-169 creature-category taxonomy for ``vision_detection`` detections.
VALID_CREATURE_CATEGORIES = ["person", "animal", "unknown_living", "not_living"]

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
# Validation error
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Raised when an event fails schema validation."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


# ---------------------------------------------------------------------------
# Envelope validation
# ---------------------------------------------------------------------------

def _validate_envelope(event: Any) -> List[str]:
    """Return a list of error messages for the event envelope fields."""
    errors = []

    if not isinstance(event, dict):
        return ["event must be a dict (JSON object)"]

    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not _UUID_RE.match(event_id):
        errors.append("event_id must be a valid UUID v4 string")

    event_type = event.get("event_type")
    if event_type not in VALID_EVENT_TYPES:
        errors.append(
            "event_type must be one of: " + ", ".join(VALID_EVENT_TYPES)
        )

    source = event.get("source")
    if source not in VALID_SOURCES:
        errors.append("source must be one of: " + ", ".join(VALID_SOURCES))

    ts = event.get("timestamp")
    if not isinstance(ts, str) or not _ISO8601_RE.match(ts):
        errors.append(
            "timestamp must be an ISO 8601 UTC string ending in Z "
            "(e.g. 2026-01-01T00:00:00Z)"
        )

    payload = event.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload must be a dict (JSON object)")

    # device_id / session_id are optional pass-through fields on this
    # module's envelope (unlike the EV3 envelope, which does not carry them
    # yet — see PEN-213). Only type-check when present.
    for field in ("device_id", "session_id"):
        value = event.get(field)
        if value is not None and not isinstance(value, str):
            errors.append("{} must be a string when provided".format(field))

    return errors


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------

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

    if "bitrate" in payload and payload["bitrate"] is not None:
        if not isinstance(payload["bitrate"], int) or payload["bitrate"] < 0:
            errors.append("payload.bitrate must be a non-negative integer")

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

    for field in ("total_frames_sent", "total_frame_drops"):
        if field in payload and payload[field] is not None:
            val = payload[field]
            if not isinstance(val, int) or val < 0:
                errors.append("payload.{} must be a non-negative integer".format(field))

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

    if "interval_seconds" in payload and payload["interval_seconds"] is not None:
        interval = payload["interval_seconds"]
        if not isinstance(interval, (int, float)) or interval < 0:
            errors.append("payload.interval_seconds must be a non-negative number")

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


def _validate_connection_status_payload(payload: Any) -> List[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["connection_status payload must be a dict"]

    connected = payload.get("connected")
    if not isinstance(connected, bool):
        errors.append("payload.connected must be a boolean")

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


def _validate_detection_item(detection: Any, index: int) -> List[str]:
    errors = []
    if not isinstance(detection, dict):
        return ["payload.detections[{}] must be a dict".format(index)]

    label = detection.get("label")
    if not isinstance(label, str) or not label.strip():
        errors.append("payload.detections[{}].label must be a non-empty string".format(index))

    creature_category = detection.get("creature_category")
    if creature_category not in VALID_CREATURE_CATEGORIES:
        errors.append(
            "payload.detections[{}].creature_category must be one of: {}".format(
                index, ", ".join(VALID_CREATURE_CATEGORIES)
            )
        )

    confidence = detection.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not (0 <= confidence <= 1):
        errors.append("payload.detections[{}].confidence must be a number between 0 and 1".format(index))

    bbox_norm = detection.get("bbox_norm")
    if (
        not isinstance(bbox_norm, list)
        or len(bbox_norm) != 4
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in bbox_norm)
    ):
        errors.append(
            "payload.detections[{}].bbox_norm must be a list of exactly 4 numbers "
            "in [0, 1] ([x_min, y_min, x_max, y_max])".format(index)
        )

    if "track_id" in detection and detection["track_id"] is not None:
        if not isinstance(detection["track_id"], int) or isinstance(detection["track_id"], bool):
            errors.append("payload.detections[{}].track_id must be an integer".format(index))

    return errors


def _validate_vision_detection_payload(payload: Any) -> List[str]:
    """Validate a ``vision_detection`` payload (PEN-169 spec)."""
    errors = []
    if not isinstance(payload, dict):
        return ["vision_detection payload must be a dict"]

    frame_index = payload.get("frame_index")
    if not isinstance(frame_index, int) or isinstance(frame_index, bool) or frame_index < 0:
        errors.append("payload.frame_index must be a non-negative integer")

    model_id = payload.get("model_id")
    if not isinstance(model_id, str) or not model_id.strip():
        errors.append("payload.model_id must be a non-empty string")

    detections = payload.get("detections")
    if not isinstance(detections, list):
        errors.append("payload.detections must be a list (may be empty)")
        detections = []
    else:
        for i, detection in enumerate(detections):
            errors.extend(_validate_detection_item(detection, i))

    detection_count = payload.get("detection_count")
    if not isinstance(detection_count, int) or isinstance(detection_count, bool) or detection_count < 0:
        errors.append("payload.detection_count must be a non-negative integer")
    elif isinstance(payload.get("detections"), list) and detection_count != len(payload["detections"]):
        errors.append("payload.detection_count must equal len(payload.detections)")

    if "analysis_fps" in payload and payload["analysis_fps"] is not None:
        val = payload["analysis_fps"]
        if not isinstance(val, (int, float)) or isinstance(val, bool) or val <= 0:
            errors.append("payload.analysis_fps must be a positive number")

    if "inference_latency_ms" in payload and payload["inference_latency_ms"] is not None:
        val = payload["inference_latency_ms"]
        if not isinstance(val, (int, float)) or isinstance(val, bool) or val < 0:
            errors.append("payload.inference_latency_ms must be a non-negative number")

    if "model_version" in payload and payload["model_version"] is not None:
        if not isinstance(payload["model_version"], str):
            errors.append("payload.model_version must be a string")

    if "scene_summary" in payload and payload["scene_summary"] is not None:
        if not isinstance(payload["scene_summary"], str):
            errors.append("payload.scene_summary must be a string")

    return errors


_PAYLOAD_VALIDATORS = {
    "video_stream_start": _validate_video_stream_start_payload,
    "video_stream_stop": _validate_video_stream_stop_payload,
    "video_stream_health": _validate_video_stream_health_payload,
    "device_status": _validate_device_status_payload,
    "connection_status": _validate_connection_status_payload,
    "error": _validate_error_payload,
    "vision_detection": _validate_vision_detection_payload,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_payload(event_type: str, payload: Any) -> None:
    """Validate the payload for a specific event type.

    Raises ``ValidationError`` if the payload is invalid.
    """
    errors = []

    validator = _PAYLOAD_VALIDATORS.get(event_type)
    if validator:
        errors.extend(validator(payload))

    if errors:
        raise ValidationError(errors)


def validate_event(event: Any) -> None:
    """Validate a complete telemetry event (envelope + payload).

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
