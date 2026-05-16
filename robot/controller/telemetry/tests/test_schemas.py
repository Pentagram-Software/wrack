"""Unit tests for robot/controller/telemetry/schemas.py."""
import uuid
from datetime import datetime, timezone

import pytest

from telemetry.schemas import (
    VALID_EVENT_TYPES,
    VALID_SOURCES,
    P0_EVENT_TYPES,
    ValidationError,
    is_valid_event,
    validate_event,
    validate_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    """Return a valid ISO 8601 UTC timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uid() -> str:
    return str(uuid.uuid4())


def _make_event(event_type: str, payload: dict, **overrides) -> dict:
    """Build a minimal valid event envelope."""
    base = {
        "event_id": _uid(),
        "event_type": event_type,
        "source": "ev3",
        "timestamp": _ts(),
        "payload": payload,
    }
    base.update(overrides)
    return base


def _battery_payload(**overrides) -> dict:
    p = {"voltage_mv": 7200, "percentage": 85.0}
    p.update(overrides)
    return p


def _command_received_payload(**overrides) -> dict:
    p = {"command": "forward"}
    p.update(overrides)
    return p


def _command_executed_payload(**overrides) -> dict:
    p = {"command": "forward", "success": True}
    p.update(overrides)
    return p


def _device_status_payload(**overrides) -> dict:
    p = {"device_name": "drive_L", "status": "connected"}
    p.update(overrides)
    return p


def _error_payload(**overrides) -> dict:
    p = {"error_type": "device_error", "message": "Motor stalled"}
    p.update(overrides)
    return p


def _api_request_payload(**overrides) -> dict:
    p = {"endpoint": "controlRobot", "status_code": 200, "latency_ms": 120.5}
    p.update(overrides)
    return p


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_p0_event_types_subset_of_all(self):
        for t in P0_EVENT_TYPES:
            assert t in VALID_EVENT_TYPES

    def test_valid_sources_contains_ev3(self):
        assert "ev3" in VALID_SOURCES

    def test_valid_sources_contains_cloud_functions(self):
        assert "cloud_functions" in VALID_SOURCES


# ---------------------------------------------------------------------------
# Envelope validation
# ---------------------------------------------------------------------------

class TestEnvelopeValidation:
    def test_valid_minimal_event_passes(self):
        event = _make_event("battery_status", _battery_payload())
        validate_event(event)  # should not raise

    def test_valid_full_event_passes(self):
        event = _make_event(
            "battery_status",
            _battery_payload(),
            session_id=_uid(),
            device_id="ev3-001",
            version="1.0",
            tags=["test"],
            correlation_id=_uid(),
        )
        validate_event(event)

    def test_non_dict_raises(self):
        with pytest.raises(ValidationError):
            validate_event("not a dict")

    def test_missing_event_id_raises(self):
        event = _make_event("battery_status", _battery_payload())
        del event["event_id"]
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert any("event_id" in e for e in exc_info.value.errors)

    def test_invalid_event_id_uuid_raises(self):
        event = _make_event("battery_status", _battery_payload(),
                            event_id="not-a-uuid")
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert any("event_id" in e for e in exc_info.value.errors)

    def test_invalid_event_type_raises(self):
        event = _make_event("unknown_type", {})
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert any("event_type" in e for e in exc_info.value.errors)

    def test_invalid_source_raises(self):
        event = _make_event("battery_status", _battery_payload(),
                            source="invalid_source")
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert any("source" in e for e in exc_info.value.errors)

    def test_invalid_timestamp_raises(self):
        event = _make_event("battery_status", _battery_payload(),
                            timestamp="2026-01-01 00:00:00")
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert any("timestamp" in e for e in exc_info.value.errors)

    def test_timestamp_without_z_raises(self):
        event = _make_event("battery_status", _battery_payload(),
                            timestamp="2026-01-01T00:00:00+00:00")
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert any("timestamp" in e for e in exc_info.value.errors)

    def test_missing_payload_raises(self):
        event = _make_event("battery_status", _battery_payload())
        del event["payload"]
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert any("payload" in e for e in exc_info.value.errors)

    def test_non_dict_payload_raises(self):
        event = _make_event("battery_status", "not-a-dict")  # type: ignore
        with pytest.raises(ValidationError):
            validate_event(event)

    def test_all_valid_event_types_accepted(self):
        for et in VALID_EVENT_TYPES:
            event = _make_event(et, {})
            # Non-P0 types have no payload validator, so only envelope checked
            if et not in P0_EVENT_TYPES:
                validate_event(event)


# ---------------------------------------------------------------------------
# battery_status payload
# ---------------------------------------------------------------------------

class TestBatteryStatusPayload:
    def test_valid_minimal(self):
        validate_payload("battery_status", _battery_payload())

    def test_valid_full(self):
        validate_payload("battery_status", {
            "voltage_mv": 7200,
            "voltage_v": 7.2,
            "current_ma": 450.0,
            "percentage": 85.0,
            "battery_type": "rechargeable",
            "is_critical": False,
        })

    def test_missing_voltage_mv_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("battery_status", {"percentage": 85.0})
        assert any("voltage_mv" in e for e in exc_info.value.errors)

    def test_negative_voltage_mv_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("battery_status", _battery_payload(voltage_mv=-1))

    def test_float_voltage_mv_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("battery_status", _battery_payload(voltage_mv=7.2))
        assert any("voltage_mv" in e for e in exc_info.value.errors)

    def test_missing_percentage_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("battery_status", {"voltage_mv": 7200})
        assert any("percentage" in e for e in exc_info.value.errors)

    def test_percentage_over_100_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("battery_status", _battery_payload(percentage=101))

    def test_percentage_below_0_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("battery_status", _battery_payload(percentage=-1))

    def test_invalid_battery_type_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("battery_status", _battery_payload(battery_type="lithium"))

    def test_is_critical_non_bool_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("battery_status", _battery_payload(is_critical="yes"))

    def test_all_valid_battery_types(self):
        for bt in ["rechargeable", "alkaline", "unknown"]:
            validate_payload("battery_status", _battery_payload(battery_type=bt))


# ---------------------------------------------------------------------------
# command_received payload
# ---------------------------------------------------------------------------

class TestCommandReceivedPayload:
    def test_valid_minimal(self):
        validate_payload("command_received", _command_received_payload())

    def test_valid_full(self):
        validate_payload("command_received", {
            "command": "forward",
            "params": {"speed": 500, "duration": 2},
            "controller_type": "ps4",
            "received_at_ms": 123456.789,
        })

    def test_missing_command_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("command_received", {})
        assert any("command" in e for e in exc_info.value.errors)

    def test_empty_command_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("command_received", _command_received_payload(command=""))

    def test_invalid_controller_type_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("command_received",
                             _command_received_payload(controller_type="gamepad"))

    def test_valid_controller_types(self):
        for ct in ["ps4", "network_remote", "unknown"]:
            validate_payload("command_received",
                             _command_received_payload(controller_type=ct))


# ---------------------------------------------------------------------------
# command_executed payload
# ---------------------------------------------------------------------------

class TestCommandExecutedPayload:
    def test_valid_minimal(self):
        validate_payload("command_executed", _command_executed_payload())

    def test_valid_with_failure(self):
        validate_payload("command_executed", {
            "command": "forward",
            "success": False,
            "duration_ms": 50.0,
            "error_message": "Motor stalled",
        })

    def test_missing_command_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("command_executed", {"success": True})

    def test_missing_success_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("command_executed", {"command": "forward"})
        assert any("success" in e for e in exc_info.value.errors)

    def test_success_non_bool_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("command_executed",
                             _command_executed_payload(success="yes"))  # type: ignore

    def test_negative_duration_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("command_executed",
                             _command_executed_payload(duration_ms=-1))


# ---------------------------------------------------------------------------
# device_status payload
# ---------------------------------------------------------------------------

class TestDeviceStatusPayload:
    def test_valid_minimal(self):
        validate_payload("device_status", _device_status_payload())

    def test_valid_full(self):
        validate_payload("device_status", {
            "device_name": "drive_L",
            "device_type": "motor",
            "port": "A",
            "status": "connected",
            "previous_status": "disconnected",
            "error_message": None,
        })

    def test_missing_device_name_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("device_status", {"status": "connected"})
        assert any("device_name" in e for e in exc_info.value.errors)

    def test_missing_status_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("device_status", {"device_name": "drive_L"})
        assert any("status" in e for e in exc_info.value.errors)

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("device_status", _device_status_payload(status="broken"))

    def test_all_valid_statuses(self):
        for s in ["connected", "disconnected", "error", "stalled", "initializing"]:
            validate_payload("device_status", _device_status_payload(status=s))

    def test_invalid_device_type_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("device_status",
                             _device_status_payload(device_type="antenna"))

    def test_all_valid_device_types(self):
        for dt in ["motor", "sensor", "controller", "unknown"]:
            validate_payload("device_status", _device_status_payload(device_type=dt))


# ---------------------------------------------------------------------------
# error payload
# ---------------------------------------------------------------------------

class TestErrorPayload:
    def test_valid_minimal(self):
        validate_payload("error", _error_payload())

    def test_valid_full(self):
        validate_payload("error", {
            "error_type": "device_error",
            "error_code": "MOTOR_STALL",
            "message": "Left drive motor stalled",
            "component": "DeviceManager",
            "stack_trace": "Traceback ...",
            "context": {"port": "A"},
        })

    def test_missing_error_type_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("error", {"message": "Something went wrong"})
        assert any("error_type" in e for e in exc_info.value.errors)

    def test_missing_message_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("error", {"error_type": "device_error"})
        assert any("message" in e for e in exc_info.value.errors)

    def test_empty_error_type_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("error", _error_payload(error_type=""))

    def test_empty_message_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("error", _error_payload(message="  "))


# ---------------------------------------------------------------------------
# api_request payload
# ---------------------------------------------------------------------------

class TestApiRequestPayload:
    def test_valid_minimal(self):
        validate_payload("api_request", _api_request_payload())

    def test_valid_full(self):
        validate_payload("api_request", {
            "endpoint": "controlRobot",
            "method": "POST",
            "command": "forward",
            "status_code": 200,
            "latency_ms": 150.5,
            "robot_response_time_ms": 120.0,
            "client_ip_hash": "abc123",
            "error_message": None,
        })

    def test_missing_endpoint_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("api_request", {"status_code": 200, "latency_ms": 100})
        assert any("endpoint" in e for e in exc_info.value.errors)

    def test_missing_status_code_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("api_request", {"endpoint": "controlRobot", "latency_ms": 100})
        assert any("status_code" in e for e in exc_info.value.errors)

    def test_invalid_status_code_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("api_request", _api_request_payload(status_code=99))

    def test_status_code_600_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("api_request", _api_request_payload(status_code=600))

    def test_negative_latency_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("api_request", _api_request_payload(latency_ms=-1))

    def test_missing_latency_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_payload("api_request", {"endpoint": "controlRobot", "status_code": 200})
        assert any("latency_ms" in e for e in exc_info.value.errors)

    def test_invalid_method_raises(self):
        with pytest.raises(ValidationError):
            validate_payload("api_request", _api_request_payload(method="CONNECT"))

    def test_all_valid_http_methods(self):
        for m in ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]:
            validate_payload("api_request", _api_request_payload(method=m))

    def test_4xx_status_code_valid(self):
        validate_payload("api_request", _api_request_payload(status_code=404))

    def test_5xx_status_code_valid(self):
        validate_payload("api_request", _api_request_payload(status_code=502))


# ---------------------------------------------------------------------------
# is_valid_event helper
# ---------------------------------------------------------------------------

class TestIsValidEvent:
    def test_returns_true_for_valid_event(self):
        event = _make_event("battery_status", _battery_payload())
        assert is_valid_event(event) is True

    def test_returns_false_for_invalid_event(self):
        assert is_valid_event({"event_type": "bad"}) is False

    def test_returns_false_for_non_dict(self):
        assert is_valid_event(None) is False


# ---------------------------------------------------------------------------
# End-to-end: full event validation for each P0 type
# ---------------------------------------------------------------------------

class TestFullEventValidation:
    def test_battery_status_event(self):
        event = _make_event("battery_status", _battery_payload(
            voltage_v=7.2,
            current_ma=450,
            battery_type="rechargeable",
            is_critical=False,
        ))
        validate_event(event)

    def test_command_received_event(self):
        event = _make_event("command_received", _command_received_payload(
            params={"speed": 500},
            controller_type="network_remote",
        ))
        validate_event(event)

    def test_command_executed_event(self):
        event = _make_event("command_executed", _command_executed_payload(
            duration_ms=45.2,
        ))
        validate_event(event)

    def test_device_status_event(self):
        event = _make_event("device_status", _device_status_payload(
            port="A",
            device_type="motor",
            previous_status="disconnected",
        ))
        validate_event(event)

    def test_error_event(self):
        event = _make_event("error", _error_payload(
            error_code="MOTOR_STALL",
            component="DeviceManager",
        ), source="ev3")
        validate_event(event)

    def test_api_request_event(self):
        event = _make_event("api_request", _api_request_payload(
            method="POST",
            command="forward",
        ), source="cloud_functions")
        validate_event(event)
