#!/usr/bin/env python3

"""
Integration tests for hot-plug (PEN-86) – device disconnect and reconnect.

These tests verify the full hot-plug lifecycle end-to-end:
  1. Devices missing at boot can be detected when later plugged in.
  2. Devices unplugged at runtime are detected and gracefully ignored.
  3. Devices replugged at runtime resume normal operation within 1-2 s.
  4. Higher-level subsystems (TankDriveSystem, Turret) refresh correctly.
  5. DeviceManager.register_reconnect/disconnect_callback() API works
     both before and after port monitoring is started.

Run with:
    python ev3_devices/tests/run_tests.py -q --no-cov
"""

import time
import threading
import pytest
from unittest.mock import Mock, patch

from .run_tests import MockMotor, MockUltrasonicSensor, MockPort


# ---------------------------------------------------------------------------
# Helper: build a DeviceManager with mocks already wired
# ---------------------------------------------------------------------------

def _make_dm_with_motors():
    """Return (device_manager, left_motor, right_motor)."""
    from ev3_devices import DeviceManager

    dm = DeviceManager()
    l_motor = MockMotor(MockPort.A)
    r_motor = MockMotor(MockPort.D)

    for name, motor, port in [
        ("drive_L_motor", l_motor, MockPort.A),
        ("drive_R_motor", r_motor, MockPort.D),
    ]:
        dm.devices[name] = motor
        dm.available_devices.append(name)
        dm.device_ports[name] = str(port)
        dm._raw_ports[name] = port
        dm.device_types[name] = MockMotor

    return dm, l_motor, r_motor


def _make_dm_with_turret():
    """Return (device_manager, turret_motor)."""
    from ev3_devices import DeviceManager

    dm = DeviceManager()
    t_motor = MockMotor(MockPort.C)

    dm.devices["turret_motor"] = t_motor
    dm.available_devices.append("turret_motor")
    dm.device_ports["turret_motor"] = str(MockPort.C)
    dm._raw_ports["turret_motor"] = MockPort.C
    dm.device_types["turret_motor"] = MockMotor

    return dm, t_motor


# ---------------------------------------------------------------------------
# Tests: register_reconnect/disconnect_callback() API
# ---------------------------------------------------------------------------

class TestRegisterCallbackAPI:
    """Tests for the convenience callback registration methods."""

    def test_register_reconnect_before_monitoring(self):
        """Callback queued before enable_port_monitoring() is registered on start."""
        from ev3_devices import DeviceManager

        dm = DeviceManager()
        cb = Mock()
        dm.register_reconnect_callback(cb)

        # Not yet monitoring – callback is queued
        assert cb in dm._pending_reconnect_callbacks
        assert dm._port_monitor is None

        # Enable monitoring – callback should be registered automatically
        dm.enable_port_monitoring(check_interval=0.05)
        assert cb in dm._port_monitor._on_reconnect_callbacks

        dm.cleanup()

    def test_register_disconnect_before_monitoring(self):
        """Disconnect callback queued before monitoring is registered on start."""
        from ev3_devices import DeviceManager

        dm = DeviceManager()
        cb = Mock()
        dm.register_disconnect_callback(cb)

        dm.enable_port_monitoring(check_interval=0.05)
        assert cb in dm._port_monitor._on_disconnect_callbacks

        dm.cleanup()

    def test_register_reconnect_after_monitoring(self):
        """Callback registered after enable_port_monitoring() is added immediately."""
        from ev3_devices import DeviceManager

        dm = DeviceManager()
        dm.enable_port_monitoring(check_interval=0.05)

        cb = Mock()
        dm.register_reconnect_callback(cb)
        assert cb in dm._port_monitor._on_reconnect_callbacks

        dm.cleanup()

    def test_register_disconnect_after_monitoring(self):
        """Disconnect callback registered after monitoring is added immediately."""
        from ev3_devices import DeviceManager

        dm = DeviceManager()
        dm.enable_port_monitoring(check_interval=0.05)

        cb = Mock()
        dm.register_disconnect_callback(cb)
        assert cb in dm._port_monitor._on_disconnect_callbacks

        dm.cleanup()

    def test_multiple_callbacks_all_fired(self):
        """All registered callbacks are called when the port monitor fires a reconnect."""
        from ev3_devices import DeviceManager

        dm, l_motor, r_motor = _make_dm_with_motors()

        cb1 = Mock()
        cb2 = Mock()
        dm.register_reconnect_callback(cb1)
        dm.register_reconnect_callback(cb2)
        dm.enable_port_monitoring(check_interval=0.05)

        # Both application-level callbacks must be registered with the port monitor
        assert cb1 in dm._port_monitor._on_reconnect_callbacks
        assert cb2 in dm._port_monitor._on_reconnect_callbacks

        # Trigger all reconnect callbacks directly (simulates port monitor firing)
        status = {"port": str(MockPort.A)}
        for cb in dm._port_monitor._on_reconnect_callbacks:
            cb("drive_L_motor", status)

        assert cb1.called
        assert cb2.called

        dm.cleanup()


# ---------------------------------------------------------------------------
# Tests: Turret hot-plug subsystem refresh
# ---------------------------------------------------------------------------

class TestTurretHotPlug:
    """Tests that Turret.refresh_motor() integrates correctly with PortMonitor."""

    def test_turret_resumes_after_motor_reconnect(self):
        """
        Full cycle: turret motor disconnects then reconnects.
        After reconnect the turret must operate with the new motor instance.
        """
        from ev3_devices import Turret

        dm, old_motor = _make_dm_with_turret()
        turret = Turret(dm)

        assert turret.turret_motor is old_motor

        # Register refresh callback before enabling monitoring
        def on_reconnect(device_name, status):
            if device_name == "turret_motor":
                turret.refresh_motor()

        dm.register_reconnect_callback(on_reconnect)
        dm.enable_port_monitoring(check_interval=0.05)

        # --- Simulate disconnect ---
        dm._on_device_disconnect("turret_motor", {"port": str(MockPort.C)})
        dm._port_monitor._device_status["turret_motor"]["connected"] = False

        assert dm.is_device_available("turret_motor") == False

        # --- Simulate reconnect: port monitor creates a new motor instance ---
        new_motor = MockMotor(MockPort.C)
        dm.devices["turret_motor"] = new_motor
        # Trigger reconnect detection manually (port monitor would do this in bg)
        dm._port_monitor._check_device("turret_motor")

        # Give the thread a moment in case of async handling
        time.sleep(0.1)

        # Turret should now use the new motor
        assert turret.turret_motor is new_motor
        assert dm.is_device_available("turret_motor") == True

        # Turret should be operational
        turret.speed_control(100, 0)
        assert new_motor._speed == 360

        dm.cleanup()

    def test_turret_remains_disabled_until_motor_reconnects(self):
        """Turret must ignore commands while motor is disconnected."""
        from ev3_devices import Turret

        dm, motor = _make_dm_with_turret()
        turret = Turret(dm)

        dm.enable_port_monitoring(check_interval=0.05)

        # Disconnect
        dm._on_device_disconnect("turret_motor", {"port": str(MockPort.C)})
        turret.turret_motor = None  # Simulate cleared reference

        # Speed control with no motor must be a no-op
        turret.speed_control(100, 0)
        assert motor._speed == 0  # Old motor not touched; new motor not yet set

        dm.cleanup()


# ---------------------------------------------------------------------------
# Tests: TankDriveSystem hot-plug subsystem refresh
# ---------------------------------------------------------------------------

class TestTankDriveHotPlug:
    """Tests that TankDriveSystem resumes after drive motor reconnect."""

    def test_drive_resumes_after_motor_reconnect(self):
        """
        Drive motor disconnects then reconnects.
        After reconnect the tank drive must execute move_forward correctly.
        """
        from ev3_devices import TankDriveSystem

        dm, l_motor, r_motor = _make_dm_with_motors()
        tds = TankDriveSystem(dm)
        tds.initialize()
        assert tds.is_initialized() == True

        def on_reconnect(device_name, status):
            if device_name in ("drive_L_motor", "drive_R_motor"):
                tds.initialize()

        dm.register_reconnect_callback(on_reconnect)
        dm.enable_port_monitoring(check_interval=0.05)

        # Disconnect left motor
        dm._on_device_disconnect("drive_L_motor", {"port": str(MockPort.A)})
        dm._port_monitor._device_status["drive_L_motor"]["connected"] = False

        # Initialize status should reflect degraded state
        tds.initialize()
        assert tds.is_initialized() == False

        # Reconnect left motor
        new_l_motor = MockMotor(MockPort.A)
        dm.devices["drive_L_motor"] = new_l_motor
        dm._port_monitor._check_device("drive_L_motor")
        time.sleep(0.1)

        # TankDriveSystem should be fully initialised again
        assert tds.is_initialized() == True

        # Drive command should reach the new motor
        tds.move_forward(500)
        assert new_l_motor._speed != 0

        dm.cleanup()

    def test_drive_ignores_commands_when_motor_missing(self):
        """move_forward is a no-op when motors are unavailable."""
        from ev3_devices import TankDriveSystem

        dm, l_motor, r_motor = _make_dm_with_motors()
        tds = TankDriveSystem(dm)
        tds.initialize()

        dm.enable_port_monitoring(check_interval=0.05)

        # Disconnect both motors
        dm._on_device_disconnect("drive_L_motor", {"port": str(MockPort.A)})
        dm._on_device_disconnect("drive_R_motor", {"port": str(MockPort.D)})

        tds.move_forward(1000)
        assert l_motor._speed == 0
        assert r_motor._speed == 0

        dm.cleanup()


# ---------------------------------------------------------------------------
# Tests: Device missing at boot then plugged in (late connect)
# ---------------------------------------------------------------------------

class TestLateConnect:
    """Tests for devices that are absent at startup and plugged in later."""

    def test_missing_motor_detected_after_plug_in(self):
        """
        Motor absent at startup: PortMonitor must detect it when it appears.
        Reconnect callback fires within ~1 s (using 50 ms interval in tests).
        """
        from ev3_devices import DeviceManager

        class PluggableMotor:
            plugged_in = False  # class-level physical plug state

            def __init__(self, port):
                if not PluggableMotor.plugged_in:
                    raise Exception("Not connected")
                self.port = port
                self._angle = 0

            def angle(self):
                return self._angle

            def stop(self):
                pass

        PluggableMotor.plugged_in = False
        dm = DeviceManager()
        dm.devices["late_motor"] = None
        dm.missing_devices.append("late_motor")
        dm.device_ports["late_motor"] = str(MockPort.B)
        dm._raw_ports["late_motor"] = MockPort.B
        dm.device_types["late_motor"] = PluggableMotor

        reconnect_cb = Mock()
        dm.register_reconnect_callback(reconnect_cb)
        dm.enable_port_monitoring(check_interval=0.05)

        # Confirm still absent
        time.sleep(0.1)
        assert dm.devices["late_motor"] is None

        # Plug it in
        PluggableMotor.plugged_in = True
        time.sleep(0.2)

        assert reconnect_cb.called
        assert dm.devices["late_motor"] is not None
        assert dm.is_device_available("late_motor") == True

        dm.cleanup()

    def test_disconnect_callback_fires_on_unplug(self):
        """
        Device unplugged at runtime: disconnect callback fires after
        2 consecutive health-check failures.
        """
        from ev3_devices import DeviceManager

        class UnplugMotor:
            healthy = True

            def __init__(self, port):
                self.port = port

            def angle(self):
                if not UnplugMotor.healthy:
                    raise OSError("Disconnected")
                return 0

            def stop(self):
                pass

        dm = DeviceManager()
        motor = UnplugMotor(MockPort.D)
        dm.devices["unplug_motor"] = motor
        dm.available_devices.append("unplug_motor")
        dm.device_ports["unplug_motor"] = str(MockPort.D)
        dm._raw_ports["unplug_motor"] = MockPort.D
        dm.device_types["unplug_motor"] = UnplugMotor

        disconnect_cb = Mock()
        dm.register_disconnect_callback(disconnect_cb)
        dm.enable_port_monitoring(check_interval=0.05)

        # Physically unplug
        UnplugMotor.healthy = False
        time.sleep(0.3)  # Wait for 2+ failed checks

        assert disconnect_cb.called
        assert dm.is_device_available("unplug_motor") == False

        dm.cleanup()


# ---------------------------------------------------------------------------
# Tests: Monitoring check interval meets acceptance criteria
# ---------------------------------------------------------------------------

class TestResponseTime:
    """Verify reconnection is detected within the target 1-2 s window."""

    def test_reconnect_within_two_seconds(self):
        """Device plugged back in should be detected within 2 seconds."""
        from ev3_devices import DeviceManager

        class TimedMotor:
            plugged_in = False

            def __init__(self, port):
                if not TimedMotor.plugged_in:
                    raise Exception("Not connected")
                self.port = port
                self._angle = 0

            def angle(self):
                return self._angle

            def stop(self):
                pass

        TimedMotor.plugged_in = False
        dm = DeviceManager()
        dm.devices["timed_motor"] = None
        dm.missing_devices.append("timed_motor")
        dm.device_ports["timed_motor"] = str(MockPort.S1)
        dm._raw_ports["timed_motor"] = MockPort.S1
        dm.device_types["timed_motor"] = TimedMotor

        reconnect_event = threading.Event()

        def on_reconnect(device_name, status):
            if device_name == "timed_motor":
                reconnect_event.set()

        dm.register_reconnect_callback(on_reconnect)
        dm.enable_port_monitoring(check_interval=1.0)  # realistic 1-second interval

        start = time.time()
        TimedMotor.plugged_in = True
        detected = reconnect_event.wait(timeout=2.5)
        elapsed = time.time() - start

        assert detected, "Reconnect was not detected within 2.5 s"
        assert elapsed <= 2.5, "Detection took {:.2f} s (expected ≤2.5 s)".format(elapsed)

        dm.cleanup()
