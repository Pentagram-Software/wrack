"""
Wrack telemetry module for the EV3 robot controller.

Submodules
----------
schemas
    Event type definitions and validation utilities.
collector
    Thread-safe, buffered telemetry event collector.
"""

from telemetry.collector import TelemetryCollector
from telemetry.schemas import ValidationError, validate_event, validate_payload, is_valid_event

__all__ = [
    "TelemetryCollector",
    "ValidationError",
    "validate_event",
    "validate_payload",
    "is_valid_event",
]
