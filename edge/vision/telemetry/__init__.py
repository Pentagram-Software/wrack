"""
Wrack Raspberry Pi telemetry module (PEN-166).

Standalone counterpart to ``robot/controller/telemetry/`` for the Raspberry
Pi vision/analytics runtime. Runs on standard CPython, so none of the
MicroPython compatibility guards used by the EV3 module are needed here.

Submodules
----------
schemas
    Event type definitions and validation utilities.
collector
    :class:`RpiTelemetryCollector` — builds and buffers telemetry event dicts.
sender
    :class:`RpiTelemetrySender` — sends buffered events to the Cloud Function
    ingestion endpoint via HTTP POST with retry logic.
builder
    :func:`build_vision_detection_event` — typed builder for
    ``vision_detection`` events (PEN-169); the integration surface a future
    inference runtime will call.

Quick start::

    from telemetry.collector import RpiTelemetryCollector
    from telemetry.sender import RpiTelemetrySender

    collector = RpiTelemetryCollector()
    sender = RpiTelemetrySender(
        endpoint="https://...cloudfunctions.net/telemetryIngestion",
        api_key="<your-api-key>",
    )

    collector.collect("device_status", device_name="camera", status="connected")
    sender.flush_and_send(collector)
"""

from .builder import build_vision_detection_event
from .collector import RpiTelemetryCollector
from .schemas import (
    VALID_EVENT_TYPES,
    VALID_SOURCES,
    ValidationError,
    is_valid_event,
    validate_event,
    validate_payload,
)
from .sender import NonRetryablePartialFailureError, PartialFailureError, RpiTelemetrySender

__version__ = "1.0.0"
__all__ = [
    "RpiTelemetryCollector",
    "RpiTelemetrySender",
    "PartialFailureError",
    "NonRetryablePartialFailureError",
    "validate_event",
    "validate_payload",
    "is_valid_event",
    "ValidationError",
    "VALID_EVENT_TYPES",
    "VALID_SOURCES",
    "build_vision_detection_event",
]
