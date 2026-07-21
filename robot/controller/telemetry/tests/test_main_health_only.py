"""Regression coverage for PEN-233's main.py health-only runtime wiring."""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


MAIN_PATH = Path(__file__).resolve().parents[2] / "main.py"


class _Speaker:
    def beep(self, *args, **kwargs):
        pass

    def say(self, *args, **kwargs):
        pass


class _EV3Brick:
    def __init__(self):
        self.speaker = _Speaker()


class _DeviceManager:
    def __init__(self, ev3):
        self.ev3 = ev3

    def try_init_device(self, *args, **kwargs):
        return None

    def are_devices_available(self, names):
        return False

    def is_device_available(self, name):
        return False

    def get_battery_info(self, battery_type="rechargeable"):
        return {
            "voltage_mv": 7500,
            "current_ma": 500,
            "percentage": 90.0,
            "battery_type": battery_type,
            "available": True,
        }

    def get_motor_availability(self):
        return {
            "drive_L_motor": True,
            "drive_R_motor": True,
            "turret_motor": False,
        }

    def print_device_status(self):
        pass

    def register_reconnect_callback(self, callback):
        pass

    def register_disconnect_callback(self, callback):
        pass

    def enable_port_monitoring(self, check_interval):
        pass

    def cleanup(self):
        pass


class _DeviceSystem:
    def __init__(self, device_manager):
        self.device_manager = device_manager

    def initialize(self):
        pass

    def __getattr__(self, name):
        return MagicMock()


class _Controller:
    def __init__(self):
        self.set_telemetry_collector = MagicMock()
        self.set_debug_input = MagicMock()
        self.start = MagicMock()
        self.stop = MagicMock()

    def is_connected(self):
        return False

    def __getattr__(self, name):
        return MagicMock()


class _Collector:
    def __init__(self, source):
        self.source = source


class _HeartbeatSender:
    def __init__(
        self,
        collector,
        sender,
        interval=30,
        battery_info_provider=None,
        motor_status_provider=None,
    ):
        self.collector = collector
        self.sender = sender
        self.interval = interval
        self.battery_info_provider = battery_info_provider
        self.motor_status_provider = motor_status_provider
        self.start = MagicMock()
        self.stop = MagicMock()


class _TelemetrySender:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.flush_and_send = MagicMock()
        self.__class__.instances.append(self)


def _module(name, **attributes):
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


def _load_health_only_main(monkeypatch):
    _TelemetrySender.instances = []
    status_collector = MagicMock()
    flush_thread = MagicMock()

    monkeypatch.setitem(sys.modules, "pybricks", _module("pybricks"))
    monkeypatch.setitem(sys.modules, "pybricks.hubs", _module("pybricks.hubs", EV3Brick=_EV3Brick))
    monkeypatch.setitem(
        sys.modules,
        "pybricks.parameters",
        _module(
            "pybricks.parameters",
            Port=types.SimpleNamespace(A="A", C="C", D="D", S2="S2", S3="S3"),
            Stop=object(),
            Direction=object(),
            Button=object(),
            Color=object(),
            SoundFile=object(),
            ImageFile=object(),
            Align=object(),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "pybricks.ev3devices",
        _module(
            "pybricks.ev3devices",
            Motor=object(),
            TouchSensor=object(),
            ColorSensor=object(),
            InfraredSensor=object(),
            UltrasonicSensor=object(),
            GyroSensor=object(),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "robot_controllers",
        _module(
            "robot_controllers",
            MIN_JOYSTICK_MOVE=10,
            PS4Controller=_Controller,
            RemoteController=_Controller,
            wait_for_connection=lambda controller: (False, 0),
        ),
    )
    monkeypatch.setitem(sys.modules, "TerrainScanner", _module("TerrainScanner", TerrainScanner=None))
    monkeypatch.setitem(
        sys.modules,
        "wake_word",
        _module("wake_word", WakeWordDetector=types.SimpleNamespace(is_available=lambda: False)),
    )
    monkeypatch.setitem(sys.modules, "threading_compat", _module("threading_compat", wait_for_workers=MagicMock()))
    monkeypatch.setitem(sys.modules, "pixy_camera", _module("pixy_camera", Pixy2Camera=object()))
    monkeypatch.setitem(
        sys.modules,
        "ev3_devices",
        _module(
            "ev3_devices",
            DeviceManager=_DeviceManager,
            TankDriveSystem=_DeviceSystem,
            Turret=_DeviceSystem,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "telemetry",
        _module(
            "telemetry",
            TelemetryCollector=_Collector,
            TelemetrySender=_TelemetrySender,
            StatusCollector=status_collector,
            HeartbeatSender=_HeartbeatSender,
            DEFAULT_HEARTBEAT_SEND_TIMEOUT_S=5,
            DEFAULT_HEARTBEAT_SEND_MAX_RETRIES=0,
            is_analytics_enabled=lambda value: value is True,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "telemetry_config",
        _module(
            "telemetry_config",
            TELEMETRY_ENDPOINT="https://example.invalid/unifiedIngress",
            TELEMETRY_DEVICE_ID="ev3-001",
            TELEMETRY_DEVICE_TOKEN="test-token",
            TELEMETRY_ANALYTICS_ENABLED=False,
        ),
    )
    monkeypatch.setitem(sys.modules, "threading", _module("threading", Thread=flush_thread))

    module_name = "main_health_only_test"
    spec = importlib.util.spec_from_file_location(module_name, MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    module.sleep = MagicMock()
    return module, status_collector, flush_thread


def test_health_only_main_disables_analytics_paths_and_starts_heartbeat(monkeypatch):
    module, status_collector, flush_thread = _load_health_only_main(monkeypatch)

    assert module._telemetry_sender is None
    assert module._heartbeat_sender is not None
    assert len(_TelemetrySender.instances) == 1
    assert _TelemetrySender.instances[0].kwargs["max_retries"] == 0
    assert _TelemetrySender.instances[0].kwargs["timeout"] == 5

    module._runtime_controller.set_telemetry_collector.assert_not_called()
    module._runtime_remote_controller.set_telemetry_collector.assert_not_called()
    status_collector.assert_not_called()
    flush_thread.assert_not_called()
    module._heartbeat_sender.start.assert_called_once_with()

    # PEN-234: the heartbeat is wired with a battery_info_provider that reads
    # from the module's device_manager, so the health-only baseline restores
    # battery reporting via the same tracked heartbeat send, not a second
    # (buffered/analytics) collection path.
    assert module._heartbeat_sender.battery_info_provider is not None
    battery_info = module._heartbeat_sender.battery_info_provider()
    assert battery_info == {
        "voltage_mv": 7500,
        "current_ma": 500,
        "percentage": 90.0,
        "battery_type": "rechargeable",
        "available": True,
    }

    # PEN-200: the heartbeat is likewise wired with a motor_status_provider
    # that reads motor availability from the module's device_manager.
    assert module._heartbeat_sender.motor_status_provider is not None
    motor_status = module._heartbeat_sender.motor_status_provider()
    assert motor_status == {
        "drive_L_motor": True,
        "drive_R_motor": True,
        "turret_motor": False,
    }

    module.quit(None)

    module._heartbeat_sender.stop.assert_called_once_with()
    _TelemetrySender.instances[0].flush_and_send.assert_not_called()
