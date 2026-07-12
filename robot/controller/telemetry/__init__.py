"""
Wrack telemetry module for the EV3 robot controller.

Submodules
----------
schemas
    Event type definitions and validation utilities.
collector
    :class:`TelemetryCollector` — builds and buffers telemetry event dicts.
sender
    :class:`TelemetrySender` — sends buffered events to the Cloud Function
    ingestion endpoint via HTTP POST with retry logic.
status_collector
    Periodic battery/motor telemetry and immediate device-change events
    (StatusCollector — PEN-124).

Quick start::

    from telemetry import TelemetryCollector, TelemetrySender

    collector = TelemetryCollector(source="ev3")
    sender = TelemetrySender(
        endpoint="https://...cloudfunctions.net/unifiedIngress",
        device_id="ev3-001",
        device_token="<your-per-device-token>",
    )

    collector.collect_battery_status(voltage_mv=7500, percentage=90.0)
    sender.flush_and_send(collector)
"""

from .collector import TelemetryCollector
from .sender import TelemetrySender, PartialFailureError
from .status_collector import (
    StatusCollector,
    DEFAULT_BATTERY_INTERVAL,
    DEFAULT_MOTOR_INTERVAL,
)
from .schemas import (
    validate_event,
    validate_payload,
    is_valid_event,
    ValidationError,
    VALID_EVENT_TYPES,
    VALID_SOURCES,
    P0_EVENT_TYPES,
)

__version__ = "1.0.0"
__all__ = [
    "TelemetryCollector",
    "TelemetrySender",
    "PartialFailureError",
    # Status collector (PEN-124)
    "StatusCollector",
    "DEFAULT_BATTERY_INTERVAL",
    "DEFAULT_MOTOR_INTERVAL",
    # Schema validation
    "validate_event",
    "validate_payload",
    "is_valid_event",
    "ValidationError",
    "VALID_EVENT_TYPES",
    "VALID_SOURCES",
    "P0_EVENT_TYPES",
]
