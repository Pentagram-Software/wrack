"""Controller callbacks must not do blocking work on the PS4 reader thread.

Anything that blocks the reader for more than a few milliseconds causes the
kernel's fixed evdev ring buffer to overflow and discard input, so these
tests assert the callbacks hand such work to the background worker rather
than running it inline.
"""

import importlib.util
import sys
import threading as _real_threading
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"


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

    def __getattr__(self, name):
        return MagicMock()


class _DeviceSystem:
    def __init__(self, device_manager):
        self.device_manager = device_manager

    def initialize(self):
        pass

    def __getattr__(self, name):
        return MagicMock()


class _Controller:
    def is_connected(self):
        return False

    def __getattr__(self, name):
        return MagicMock()


def _module(name, **attributes):
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


def _load_main(monkeypatch):
    """Import main.py with its hardware dependencies stubbed out."""
    monkeypatch.setitem(sys.modules, "pybricks", _module("pybricks"))
    monkeypatch.setitem(
        sys.modules, "pybricks.hubs", _module("pybricks.hubs", EV3Brick=_EV3Brick)
    )
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
            InputDiagnostics=MagicMock(),
            wait_for_connection=lambda controller: (False, 0),
        ),
    )
    monkeypatch.setitem(
        sys.modules, "TerrainScanner", _module("TerrainScanner", TerrainScanner=None)
    )
    monkeypatch.setitem(
        sys.modules,
        "wake_word",
        _module(
            "wake_word",
            WakeWordDetector=types.SimpleNamespace(is_available=lambda: False),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "threading_compat",
        _module(
            "threading_compat",
            wait_for_workers=MagicMock(),
            create_lock=_real_threading.Lock,
            join_thread=MagicMock(return_value=False),
            thread_is_alive=MagicMock(return_value=False),
        ),
    )
    monkeypatch.setitem(
        sys.modules, "pixy_camera", _module("pixy_camera", Pixy2Camera=object())
    )
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
            TelemetryCollector=MagicMock(),
            TelemetrySender=MagicMock(),
            StatusCollector=MagicMock(),
            HeartbeatSender=MagicMock(),
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

    module_name = "main_controller_callbacks_test"
    spec = importlib.util.spec_from_file_location(module_name, MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    module.sleep = MagicMock()
    return module


@pytest.fixture
def main_module(monkeypatch):
    module = _load_main(monkeypatch)
    # Mark the worker up without starting a real thread, so submissions are
    # queued and can be inspected instead of running.
    module._action_worker._running = True
    yield module
    module._action_worker._running = False


class _FakeScanner:
    """Stands in for TerrainScanner, whose start/stop both end in a beep."""

    def __init__(self):
        self.started = 0
        self.stopped = 0

    def start_automatic_scanning(self):
        self.started += 1

    def stop_automatic_scanning(self):
        self.stopped += 1


@pytest.fixture
def scanner(main_module):
    fake = _FakeScanner()
    main_module.terrain_scanner = fake
    main_module.TerrainScanner = _FakeScanner
    return fake


class TestTerrainScannerCallbacks:
    """start/stop_automatic_scanning both end with a ~200ms speaker.beep()
    that used to run on whichever thread invoked them."""

    def test_start_is_queued_not_run_inline(self, main_module, scanner):
        main_module.start_auto_terrain_scanning(None)

        assert scanner.started == 0
        assert main_module._action_worker.pending == 1

    def test_start_still_happens_on_the_worker(self, main_module, scanner):
        main_module.start_auto_terrain_scanning(None)
        main_module._action_worker.run_pending()

        assert scanner.started == 1

    def test_stop_is_queued_not_run_inline(self, main_module, scanner):
        main_module.stop_auto_terrain_scanning(None)

        assert scanner.stopped == 0
        assert main_module._action_worker.pending == 1

    def test_stop_still_happens_on_the_worker(self, main_module, scanner):
        main_module.stop_auto_terrain_scanning(None)
        main_module._action_worker.run_pending()

        assert scanner.stopped == 1

    def test_unavailable_scanner_queues_its_beep(self, main_module):
        main_module.terrain_scanner = None

        main_module.start_auto_terrain_scanning(None)

        assert main_module._action_worker.pending == 1


class TestSpeechCallbacks:

    def test_cross_button_greeting_is_queued(self, main_module):
        """Measured at 5-7s on-device; the worst offender for dropped input."""
        main_module.sayit(None)

        assert main_module._action_worker.pending == 1

    def test_greeting_runs_inline_when_the_worker_is_down(self, main_module):
        main_module._action_worker._running = False
        spoken = []
        main_module.ev3.speaker.say = lambda text: spoken.append(text)

        main_module.sayit(None)

        assert len(spoken) == 1

    def test_a_full_queue_drops_rather_than_speaking_inline(self, main_module):
        """The reader thread must stay free even under a burst of presses."""
        spoken = []
        main_module.ev3.speaker.say = lambda text: spoken.append(text)

        for _ in range(main_module._action_worker.max_queue + 3):
            main_module.sayit(None)

        assert spoken == []
        assert main_module._action_worker.dropped_count == 3
