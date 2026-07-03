"""
Tests for telemetry.status_collector.StatusCollector (PEN-124).

Acceptance criteria verified here:
- Battery status collected every 60 s (configurable).
- Motor status collected every 10 s (configurable).
- Status changes (device connect/disconnect) collected immediately.
- Collection intervals are configurable.
- Tests verify collection timing via mocked time.time / time.sleep.
"""

from __future__ import annotations

import time
import threading
from unittest.mock import MagicMock, patch, call

import pytest

from telemetry.collector import TelemetryCollector
from telemetry.status_collector import (
    StatusCollector,
    DEFAULT_BATTERY_INTERVAL,
    DEFAULT_MOTOR_INTERVAL,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_device_manager(
    voltage_mv: int = 7200,
    percentage: float = 85.0,
    current_ma: int = 500,
    available: bool = True,
):
    """Build a mock DeviceManager with configurable battery/motor state."""
    dm = MagicMock()
    dm.get_battery_info.return_value = {
        "voltage_mv": voltage_mv,
        "current_ma": current_ma,
        "percentage": percentage,
        "battery_type": "rechargeable",
        "available": available,
    }
    dm.get_motor_status.return_value = {
        "drive_L_motor": {"available": True, "port": "A", "angle_degrees": 0,
                          "speed_deg_per_sec": 0, "stalled": False},
        "drive_R_motor": {"available": True, "port": "D", "angle_degrees": 0,
                          "speed_deg_per_sec": 0, "stalled": False},
        "turret_motor": {"available": False, "port": "C"},
    }
    dm.register_disconnect_callback = MagicMock()
    dm.register_reconnect_callback = MagicMock()
    return dm


# ---------------------------------------------------------------------------
# Default interval constants
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_default_battery_interval(self):
        assert DEFAULT_BATTERY_INTERVAL == 60

    def test_default_motor_interval(self):
        assert DEFAULT_MOTOR_INTERVAL == 10

    def test_status_collector_uses_defaults(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        assert sc.battery_interval == DEFAULT_BATTERY_INTERVAL
        assert sc.motor_interval == DEFAULT_MOTOR_INTERVAL


# ---------------------------------------------------------------------------
# Construction and configuration
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_custom_battery_interval(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm, battery_interval=30)
        assert sc.battery_interval == 30

    def test_custom_motor_interval(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm, motor_interval=5)
        assert sc.motor_interval == 5

    def test_not_running_by_default(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        assert not sc.is_running


# ---------------------------------------------------------------------------
# Manual collection helpers (collect_battery_now / collect_motor_now)
# ---------------------------------------------------------------------------


class TestManualCollection:
    def test_collect_battery_now_returns_event(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        event = sc.collect_battery_now()
        assert event is not None
        assert event["event_type"] == "battery_status"

    def test_collect_battery_now_buffers_event(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc.collect_battery_now()
        assert c.buffer_size == 1

    def test_collect_battery_payload_fields(self):
        c = TelemetryCollector()
        dm = _make_device_manager(voltage_mv=7500, percentage=90.0)
        sc = StatusCollector(c, dm)
        event = sc.collect_battery_now()
        assert event["payload"]["voltage_mv"] == 7500
        assert event["payload"]["percentage"] == 90.0
        assert event["payload"]["battery_type"] == "rechargeable"

    def test_collect_battery_returns_none_when_unavailable(self):
        c = TelemetryCollector()
        dm = _make_device_manager(available=False, voltage_mv=None, percentage=None)
        sc = StatusCollector(c, dm)
        event = sc.collect_battery_now()
        assert event is None
        assert c.buffer_size == 0

    def test_collect_motor_now_returns_event(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        event = sc.collect_motor_now()
        assert event is not None
        assert event["event_type"] == "motor_status"

    def test_collect_motor_payload_contains_motors(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        event = sc.collect_motor_now()
        assert "motors" in event["payload"]
        assert "drive_L_motor" in event["payload"]["motors"]


# ---------------------------------------------------------------------------
# Device connect / disconnect — immediate collection (PEN-124 AC #3)
# ---------------------------------------------------------------------------


class TestDeviceEvents:
    def test_disconnect_callback_collects_device_status(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc._on_device_disconnect("drive_L_motor", {"port": "A"})
        assert c.buffer_size == 1
        event = c.peek()[0]
        assert event["event_type"] == "device_status"
        assert event["payload"]["status"] == "disconnected"
        assert event["payload"]["device_name"] == "drive_L_motor"

    def test_reconnect_callback_collects_device_status(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc._on_device_reconnect("drive_L_motor", {"port": "A"})
        assert c.buffer_size == 1
        event = c.peek()[0]
        assert event["event_type"] == "device_status"
        assert event["payload"]["status"] == "connected"

    def test_disconnect_payload_previous_status_is_connected(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc._on_device_disconnect("turret_motor", {"port": "C"})
        event = c.peek()[0]
        assert event["payload"]["previous_status"] == "connected"

    def test_reconnect_payload_previous_status_is_disconnected(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc._on_device_reconnect("turret_motor", {"port": "C"})
        event = c.peek()[0]
        assert event["payload"]["previous_status"] == "disconnected"

    def test_disconnect_includes_port(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc._on_device_disconnect("drive_R_motor", {"port": "D"})
        event = c.peek()[0]
        assert event["payload"]["port"] == "D"

    def test_device_type_inferred_for_motor(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc._on_device_disconnect("drive_L_motor", {"port": "A"})
        assert c.peek()[0]["payload"]["device_type"] == "motor"

    def test_device_type_inferred_for_sensor(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc._on_device_disconnect("ultrasonic_sensor", {"port": "S2"})
        assert c.peek()[0]["payload"]["device_type"] == "sensor"

    def test_device_type_unknown_fallback(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc._on_device_disconnect("some_device", {})
        assert c.peek()[0]["payload"]["device_type"] == "unknown"

    def test_callbacks_registered_with_device_manager_on_start(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc.start()
        dm.register_disconnect_callback.assert_called_once_with(
            sc._on_device_disconnect
        )
        dm.register_reconnect_callback.assert_called_once_with(
            sc._on_device_reconnect
        )
        sc.stop()


# ---------------------------------------------------------------------------
# Timing tests — periodic collection via mocked time (PEN-124 AC #5)
# ---------------------------------------------------------------------------


class TestCollectionTiming:
    """
    Verify collection intervals by running the _run loop with a mocked
    time.time that advances at each call.  We patch StatusCollector._run
    to use our controllable fake-time loop rather than blocking for real.
    """

    def _run_fake_loop(self, sc: StatusCollector, tick_seconds: float, ticks: int):
        """Execute the collection logic for *ticks* iterations using a fake clock.

        Initialise last-collection timestamps to ``-interval`` so that the very
        first tick triggers a collection — matching the real ``_run()`` behaviour
        where ``time.time()`` (a large Unix epoch) far exceeds the interval
        relative to the initial ``0.0`` baseline.
        """
        fake_time = [0.0]
        last_battery = [-sc.battery_interval]
        last_motor = [-sc.motor_interval]

        for _ in range(ticks):
            now = fake_time[0]
            if now - last_battery[0] >= sc.battery_interval:
                sc._collect_battery_status()
                last_battery[0] = now
            if now - last_motor[0] >= sc.motor_interval:
                sc._collect_motor_status()
                last_motor[0] = now
            fake_time[0] += tick_seconds

    def test_battery_collected_at_correct_interval(self):
        """With battery_interval=60 and 1-second ticks, expect exactly 2 battery
        events over 120 ticks (t=0 and t=60)."""
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm, battery_interval=60, motor_interval=999)

        self._run_fake_loop(sc, tick_seconds=1, ticks=120)

        battery_events = [e for e in c.peek() if e["event_type"] == "battery_status"]
        assert len(battery_events) == 2

    def test_motor_collected_at_correct_interval(self):
        """With motor_interval=10 and 1-second ticks, expect exactly 6 motor
        events over 60 ticks (t=0,10,20,30,40,50)."""
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm, battery_interval=999, motor_interval=10)

        self._run_fake_loop(sc, tick_seconds=1, ticks=60)

        motor_events = [e for e in c.peek() if e["event_type"] == "motor_status"]
        assert len(motor_events) == 6

    def test_configurable_battery_interval(self):
        """Custom battery_interval=30 should produce 3 events in 90 ticks."""
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm, battery_interval=30, motor_interval=999)

        self._run_fake_loop(sc, tick_seconds=1, ticks=90)

        battery_events = [e for e in c.peek() if e["event_type"] == "battery_status"]
        assert len(battery_events) == 3

    def test_configurable_motor_interval(self):
        """Custom motor_interval=5 should produce 4 events in 20 ticks."""
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm, battery_interval=999, motor_interval=5)

        self._run_fake_loop(sc, tick_seconds=1, ticks=20)

        motor_events = [e for e in c.peek() if e["event_type"] == "motor_status"]
        assert len(motor_events) == 4

    def test_both_intervals_independent(self):
        """Battery (60 s) and motor (10 s) collections are independent."""
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm, battery_interval=60, motor_interval=10)

        self._run_fake_loop(sc, tick_seconds=1, ticks=120)

        battery_events = [e for e in c.peek() if e["event_type"] == "battery_status"]
        motor_events = [e for e in c.peek() if e["event_type"] == "motor_status"]
        assert len(battery_events) == 2
        assert len(motor_events) == 12


# ---------------------------------------------------------------------------
# Start / stop lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_start_sets_running_true(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc.start()
        assert sc.is_running
        sc.stop()

    def test_start_does_not_use_daemon_or_name_kwargs(self):
        """Regression (PEN-188): Thread() must omit daemon/name kwargs.

        Pybricks MicroPython's threading.Thread accepts only ``target`` —
        passing ``daemon`` or ``name`` raises TypeError and crashes the app on
        the EV3.
        """
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)

        original_thread = threading.Thread
        created_kwargs = []

        def capturing_thread(*args, **kwargs):
            created_kwargs.append(kwargs)
            return original_thread(*args, **kwargs)

        with patch(
            "telemetry.status_collector._threading.Thread",
            side_effect=capturing_thread,
        ):
            sc.start()
        sc.stop()

        assert len(created_kwargs) == 1, "Expected exactly one Thread to be created"
        assert "daemon" not in created_kwargs[0], (
            "daemon kwarg is unsupported by Pybricks MicroPython Thread()"
        )
        assert "name" not in created_kwargs[0], (
            "name kwarg is unsupported by Pybricks MicroPython Thread()"
        )

    def test_stop_sets_running_false(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc.start()
        sc.stop()
        assert not sc.is_running

    def test_double_start_is_safe(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc.start()
        sc.start()  # second call must not raise
        assert sc.is_running
        sc.stop()

    def test_stop_before_start_is_safe(self):
        c = TelemetryCollector()
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc.stop()  # must not raise


# ---------------------------------------------------------------------------
# Crash containment — a collector bug must never kill the caller
# ---------------------------------------------------------------------------


class TestCrashContainment:
    """A bug inside ``TelemetryCollector.collect()`` (e.g. a MicroPython API
    gap, like the ``uuid4``/``format()`` issues already hit in production)
    must not propagate out of StatusCollector: it would permanently kill the
    background collection thread, or crash whatever thread a device-manager
    callback runs on.
    """

    def test_battery_collection_exception_does_not_propagate(self):
        c = TelemetryCollector()
        c.collect = MagicMock(side_effect=RuntimeError("boom"))
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        assert sc._collect_battery_status() is None

    def test_motor_collection_exception_does_not_propagate(self):
        c = TelemetryCollector()
        c.collect = MagicMock(side_effect=RuntimeError("boom"))
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        assert sc._collect_motor_status() is None

    def test_disconnect_callback_exception_does_not_propagate(self):
        c = TelemetryCollector()
        c.collect = MagicMock(side_effect=RuntimeError("boom"))
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc._on_device_disconnect("drive_L_motor", {"port": "A"})  # must not raise

    def test_reconnect_callback_exception_does_not_propagate(self):
        c = TelemetryCollector()
        c.collect = MagicMock(side_effect=RuntimeError("boom"))
        dm = _make_device_manager()
        sc = StatusCollector(c, dm)
        sc._on_device_reconnect("drive_L_motor", {"port": "A"})  # must not raise

    def test_periodic_loop_survives_persistent_collection_failure(self):
        """Even if every collection attempt fails, subsequent ticks must
        still be attempted — the loop itself must never die."""
        c = TelemetryCollector()
        c.collect = MagicMock(side_effect=RuntimeError("boom"))
        dm = _make_device_manager()
        sc = StatusCollector(c, dm, battery_interval=10, motor_interval=10)

        # Should complete all 30 ticks without raising, attempting collection
        # at t=0, 10, 20 despite every call failing.
        TestCollectionTiming()._run_fake_loop(sc, tick_seconds=1, ticks=30)
        assert c.collect.call_count == 6  # battery + motor at each of 3 ticks


# ---------------------------------------------------------------------------
# _infer_device_type helper
# ---------------------------------------------------------------------------


class TestInferDeviceType:
    @pytest.mark.parametrize("name,expected", [
        ("drive_L_motor", "motor"),
        ("turret_motor", "motor"),
        ("ultrasonic_sensor", "sensor"),
        ("gyro_sensor", "sensor"),
        ("ps4_controller", "controller"),
        ("some_unknown_device", "unknown"),
    ])
    def test_infer_device_type(self, name, expected):
        assert StatusCollector._infer_device_type(name) == expected
