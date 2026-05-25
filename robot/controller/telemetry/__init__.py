"""
Wrack telemetry module for the EV3 robot controller.

Submodules
----------
schemas
    Event type definitions and validation utilities.
collector
    Thread-safe in-memory event buffer (TelemetryCollector).
sender
    HTTP delivery to the Cloud Function ingestion endpoint (TelemetrySender).
status_collector
    Periodic battery/motor telemetry and immediate device-change events
    (StatusCollector — PEN-124).
"""

from .collector import TelemetryCollector
from .sender import TelemetrySender, SendError
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

__all__ = [
    # Collector
    "TelemetryCollector",
    # Sender
    "TelemetrySender",
    "SendError",
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
