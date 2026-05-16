"""
Wrack Telemetry — Shared Python event type definitions.

These types mirror the canonical JSON Schema definitions in
``shared/telemetry-types/schemas/``. Keep them in sync when schemas evolve.

Usage::

    from events import EventType, EventSource, VALID_EVENT_TYPES

"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

# ---------------------------------------------------------------------------
# Enumerations (as string literals for micropython compatibility)
# ---------------------------------------------------------------------------

EventSource = Literal["ev3", "rpi", "cloud_functions", "web", "ios"]

VALID_SOURCES: List[str] = ["ev3", "rpi", "cloud_functions", "web", "ios"]

EventType = Literal[
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
]

VALID_EVENT_TYPES: List[str] = [
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
]

BatteryType = Literal["rechargeable", "alkaline", "unknown"]
ControllerType = Literal["ps4", "network_remote", "unknown"]
DeviceStatusValue = Literal["connected", "disconnected", "error", "stalled", "initializing"]
DeviceType = Literal["motor", "sensor", "controller", "unknown"]
HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

# ---------------------------------------------------------------------------
# Type aliases — using TypedDict where available, plain Dict otherwise
# ---------------------------------------------------------------------------

try:
    from typing import TypedDict

    class TelemetryEventEnvelope(TypedDict, total=False):
        """Common envelope shared by every telemetry event."""
        event_id: str               # required
        event_type: str             # required — one of VALID_EVENT_TYPES
        source: str                 # required — one of VALID_SOURCES
        timestamp: str              # required — ISO 8601 UTC
        payload: Dict[str, Any]     # required
        session_id: Optional[str]
        device_id: Optional[str]
        version: Optional[str]
        tags: Optional[List[str]]
        user_id: Optional[str]
        correlation_id: Optional[str]

    class BatteryStatusPayload(TypedDict, total=False):
        voltage_mv: int             # required
        percentage: float           # required, 0–100
        voltage_v: Optional[float]
        current_ma: Optional[float]
        battery_type: Optional[str]
        is_critical: Optional[bool]

    class CommandReceivedPayload(TypedDict, total=False):
        command: str                # required
        params: Optional[Dict[str, Any]]
        controller_type: Optional[str]
        received_at_ms: Optional[float]

    class CommandExecutedPayload(TypedDict, total=False):
        command: str                # required
        success: bool               # required
        duration_ms: Optional[float]
        error_message: Optional[str]
        params: Optional[Dict[str, Any]]
        controller_type: Optional[str]

    class DeviceStatusPayload(TypedDict, total=False):
        device_name: str            # required
        status: str                 # required — one of VALID_DEVICE_STATUSES
        device_type: Optional[str]
        port: Optional[str]
        previous_status: Optional[str]
        error_message: Optional[str]

    class ErrorPayload(TypedDict, total=False):
        error_type: str             # required
        message: str                # required
        error_code: Optional[str]
        component: Optional[str]
        stack_trace: Optional[str]
        context: Optional[Dict[str, Any]]

    class ApiRequestPayload(TypedDict, total=False):
        endpoint: str               # required
        status_code: int            # required
        latency_ms: float           # required
        method: Optional[str]
        command: Optional[str]
        robot_response_time_ms: Optional[float]
        client_ip_hash: Optional[str]
        error_message: Optional[str]

except ImportError:
    # MicroPython fallback — TypedDict is not available; use plain dicts
    TelemetryEventEnvelope = dict  # type: ignore[misc, assignment]
    BatteryStatusPayload = dict     # type: ignore[misc, assignment]
    CommandReceivedPayload = dict   # type: ignore[misc, assignment]
    CommandExecutedPayload = dict   # type: ignore[misc, assignment]
    DeviceStatusPayload = dict      # type: ignore[misc, assignment]
    ErrorPayload = dict             # type: ignore[misc, assignment]
    ApiRequestPayload = dict        # type: ignore[misc, assignment]


# ---------------------------------------------------------------------------
# Convenience constants
# ---------------------------------------------------------------------------

VALID_DEVICE_STATUSES: List[str] = [
    "connected", "disconnected", "error", "stalled", "initializing"
]

VALID_DEVICE_TYPES: List[str] = ["motor", "sensor", "controller", "unknown"]

VALID_BATTERY_TYPES: List[str] = ["rechargeable", "alkaline", "unknown"]

VALID_CONTROLLER_TYPES: List[str] = ["ps4", "network_remote", "unknown"]

VALID_HTTP_METHODS: List[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

P0_EVENT_TYPES: List[str] = [
    "battery_status",
    "command_received",
    "command_executed",
    "device_status",
    "error",
    "api_request",
]
