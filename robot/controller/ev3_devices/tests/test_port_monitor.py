#!/usr/bin/env python3

"""
Unit tests for PortMonitor class and device disconnect/reconnect handling

Run these tests using:
    python ev3_devices/tests/run_tests.py

This ensures pybricks mocks are set up before any imports.
"""

import pytest
import time
import threading
from unittest.mock import Mock, MagicMock, patch

# Import mock classes from run_tests (they are defined inline there before pybricks mocks)
from .run_tests import MockMotor, MockUltrasonicSensor, MockPort


class TestPortMonitor:
    """Tests for the PortMonitor class"""
    
    @pytest.fixture
    def device_manager(self):
        """Create a fresh DeviceManager for each test"""
        from ev3_devices import DeviceManager
        return DeviceManager()
    
    @pytest.fixture
    def port_monitor(self, device_manager):
        """Create a PortMonitor instance"""
        from ev3_devices.port_monitor import PortMonitor
        return PortMonitor(device_manager, check_interval=0.1)
    
    @pytest.fixture
    def device_manager_with_motor(self, device_manager):
        """Create a DeviceManager with a mock motor"""
        motor = MockMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        device_manager.available_devices.append("test_motor")
        device_manager.device_ports["test_motor"] = str(MockPort.A)
        device_manager.device_types["test_motor"] = MockMotor
        return device_manager, motor
    
    def test_port_monitor_initialization(self, port_monitor, device_manager):
        """Test PortMonitor initializes correctly"""
        assert port_monitor.device_manager == device_manager
        assert port_monitor.check_interval == 0.1
        assert not port_monitor.is_running()
    
    def test_register_device(self, port_monitor, device_manager_with_motor):
        """Test registering a device for monitoring"""
        device_manager, motor = device_manager_with_motor
        
        port_monitor.register_device("test_motor", MockMotor, MockPort.A)
        
        status = port_monitor.get_device_status("test_motor")
        assert status is not None
        assert status['connected'] == True
        assert status['device_type'] == MockMotor
    
    def test_start_stop_monitoring(self, port_monitor):
        """Test starting and stopping the monitoring thread"""
        port_monitor.start()
        
        # Give thread time to start
        time.sleep(0.05)
        assert port_monitor.is_running()
        
        port_monitor.stop()
        time.sleep(0.05)
        assert not port_monitor.is_running()
    
    def test_device_health_check_success(self, port_monitor, device_manager_with_motor):
        """Test health check passes for healthy device"""
        device_manager, motor = device_manager_with_motor
        
        port_monitor.register_device("test_motor", MockMotor, MockPort.A)
        
        # Health check should succeed
        is_healthy = port_monitor._perform_health_check("test_motor")
        assert is_healthy == True
    
    def test_device_health_check_failure(self, port_monitor, device_manager):
        """Test health check fails for disconnected device"""
        # Create a motor that raises exceptions
        class FailingMotor:
            def __init__(self, port):
                self.port = port
            
            def angle(self):
                raise Exception("Device disconnected")
        
        failing_motor = FailingMotor(MockPort.A)
        device_manager.devices["failing_motor"] = failing_motor
        device_manager.available_devices.append("failing_motor")
        
        port_monitor.register_device("failing_motor", FailingMotor, MockPort.A)
        
        # Health check should fail
        is_healthy = port_monitor._perform_health_check("failing_motor")
        assert is_healthy == False
    
    def test_disconnect_detection(self, port_monitor, device_manager):
        """Test that device disconnection is detected"""
        disconnect_callback = Mock()
        port_monitor.on_disconnect(disconnect_callback)
        
        # Create a motor that will fail health checks
        class DisconnectingMotor:
            def __init__(self, port):
                self.port = port
                self.connected = True
            
            def angle(self):
                if not self.connected:
                    raise Exception("Device disconnected")
                return 0
        
        motor = DisconnectingMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        device_manager.available_devices.append("test_motor")
        device_manager.device_types["test_motor"] = DisconnectingMotor
        
        port_monitor.register_device("test_motor", DisconnectingMotor, MockPort.A)
        
        # Simulate disconnection
        motor.connected = False
        
        # Run health check multiple times (need 2 failures for disconnect)
        port_monitor._check_device("test_motor")
        port_monitor._check_device("test_motor")
        
        # Callback should have been called
        assert disconnect_callback.called
        assert port_monitor.is_device_connected("test_motor") == False
    
    def test_reconnect_detection(self, port_monitor, device_manager):
        """Test that device reconnection is detected"""
        reconnect_callback = Mock()
        port_monitor.on_reconnect(reconnect_callback)
        
        # Start with a disconnected device (None in device manager)
        device_manager.devices["test_motor"] = None
        device_manager.missing_devices.append("test_motor")
        device_manager.device_types["test_motor"] = MockMotor
        device_manager.device_ports["test_motor"] = str(MockPort.A)
        
        port_monitor.register_device("test_motor", MockMotor, MockPort.A)
        
        # Mark as disconnected initially
        port_monitor._device_status["test_motor"]['connected'] = False
        
        # Now "reconnect" by adding a working motor
        motor = MockMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        
        # Run health check
        port_monitor._check_device("test_motor")
        
        # Callback should have been called
        assert reconnect_callback.called
        assert port_monitor.is_device_connected("test_motor") == True
    
    def test_get_all_device_statuses(self, port_monitor, device_manager_with_motor):
        """Test getting status of all monitored devices"""
        device_manager, motor = device_manager_with_motor
        
        port_monitor.register_device("test_motor", MockMotor, MockPort.A)
        
        # Add another device
        sensor = MockUltrasonicSensor(MockPort.S1)
        device_manager.devices["test_sensor"] = sensor
        device_manager.available_devices.append("test_sensor")
        port_monitor.register_device("test_sensor", MockUltrasonicSensor, MockPort.S1)
        
        statuses = port_monitor.get_all_device_statuses()
        
        assert "test_motor" in statuses
        assert "test_sensor" in statuses
        assert statuses["test_motor"]['connected'] == True
        assert statuses["test_sensor"]['connected'] == True
    
    def test_monitoring_thread_checks_devices(self, port_monitor, device_manager_with_motor):
        """Test that the monitoring thread actually checks devices"""
        device_manager, motor = device_manager_with_motor
        
        port_monitor.register_device("test_motor", MockMotor, MockPort.A)
        
        # Start monitoring
        port_monitor.start()
        
        # Wait for at least one check cycle
        time.sleep(0.15)
        
        # Verify last_check was updated
        status = port_monitor.get_device_status("test_motor")
        assert status['last_check'] > 0
        
        port_monitor.stop()


class TestSafeDeviceProxy:
    """Tests for the SafeDeviceProxy class"""
    
    @pytest.fixture
    def mock_motor(self):
        """Create a mock motor"""
        return MockMotor(MockPort.A)
    
    @pytest.fixture
    def safe_proxy(self, mock_motor):
        """Create a SafeDeviceProxy wrapping a mock motor"""
        from ev3_devices.port_monitor import SafeDeviceProxy
        return SafeDeviceProxy(mock_motor, "test_motor")
    
    def test_proxy_forwards_method_calls(self, safe_proxy, mock_motor):
        """Test that proxy forwards method calls to wrapped device"""
        safe_proxy.run(500)
        assert mock_motor._speed == 500
    
    def test_proxy_returns_method_results(self, safe_proxy, mock_motor):
        """Test that proxy returns results from wrapped device"""
        mock_motor._angle = 45
        result = safe_proxy.angle()
        assert result == 45
    
    def test_proxy_catches_exceptions(self, safe_proxy):
        """Test that proxy catches exceptions from disconnected device"""
        # Create a failing motor
        class FailingMotor:
            def run(self, speed):
                raise Exception("Device disconnected")
        
        from ev3_devices.port_monitor import SafeDeviceProxy
        failing_proxy = SafeDeviceProxy(FailingMotor(), "failing_motor")
        
        # Should not raise, should return None
        result = failing_proxy.run(500)
        assert result is None
        assert failing_proxy.is_enabled() == False
    
    def test_proxy_ignores_calls_when_disabled(self, safe_proxy, mock_motor):
        """Test that proxy ignores calls when disabled"""
        safe_proxy.disable()
        
        result = safe_proxy.run(500)
        
        assert result is None
        assert mock_motor._speed == 0  # Motor should not have been called
    
    def test_proxy_enable_disable(self, safe_proxy):
        """Test enabling and disabling the proxy"""
        assert safe_proxy.is_enabled() == True
        
        safe_proxy.disable()
        assert safe_proxy.is_enabled() == False
        
        safe_proxy.enable()
        assert safe_proxy.is_enabled() == True
    
    def test_proxy_with_port_monitor(self, mock_motor):
        """Test proxy checks port monitor for connectivity"""
        from ev3_devices.port_monitor import SafeDeviceProxy, PortMonitor
        from ev3_devices import DeviceManager
        
        device_manager = DeviceManager()
        device_manager.devices["test_motor"] = mock_motor
        device_manager.available_devices.append("test_motor")
        
        port_monitor = PortMonitor(device_manager)
        port_monitor.register_device("test_motor", MockMotor, MockPort.A)
        
        proxy = SafeDeviceProxy(mock_motor, "test_motor", port_monitor)
        
        # Should work when connected
        proxy.run(500)
        assert mock_motor._speed == 500
        
        # Mark as disconnected in port monitor
        port_monitor._device_status["test_motor"]['connected'] = False
        
        # Should ignore calls when disconnected
        mock_motor._speed = 0
        result = proxy.run(1000)
        assert result is None
        assert mock_motor._speed == 0
    
    def test_proxy_set_wrapped_device(self, safe_proxy):
        """Test updating the wrapped device"""
        new_motor = MockMotor(MockPort.B)
        safe_proxy.set_wrapped_device(new_motor)
        
        assert safe_proxy.get_wrapped_device() == new_motor
        assert safe_proxy.is_enabled() == True


class TestDeviceManagerDisconnectHandling:
    """Tests for DeviceManager disconnect/reconnect handling"""
    
    @pytest.fixture
    def device_manager(self):
        """Create a fresh DeviceManager"""
        from ev3_devices import DeviceManager
        return DeviceManager()
    
    def test_safe_device_call_handles_connectivity_exceptions(self, device_manager):
        """Test that safe_device_call catches connectivity exceptions from disconnected devices"""
        # Create a motor that raises a connectivity exception (OSError)
        class FailingMotor:
            def run(self, speed):
                raise OSError("Device disconnected - I/O error")
        
        failing_motor = FailingMotor()
        device_manager.devices["failing_motor"] = failing_motor
        device_manager.available_devices.append("failing_motor")
        
        # Should not raise for connectivity errors, should return None
        result = device_manager.safe_device_call("failing_motor", "run", 500)
        assert result is None
        
        # Device should be marked as disconnected
        assert device_manager.is_device_disconnected("failing_motor") == True
    
    def test_safe_device_call_reraises_non_connectivity_exceptions(self, device_manager):
        """Test that safe_device_call re-raises non-connectivity exceptions (e.g., TypeError, ValueError)"""
        # Create a motor that raises a programming error
        class BuggyMotor:
            def run(self, speed):
                raise TypeError("Invalid argument type")
        
        buggy_motor = BuggyMotor()
        device_manager.devices["buggy_motor"] = buggy_motor
        device_manager.available_devices.append("buggy_motor")
        
        # Should re-raise non-connectivity exceptions
        with pytest.raises(TypeError):
            device_manager.safe_device_call("buggy_motor", "run", "not_a_number")
        
        # Device should NOT be marked as disconnected
        assert device_manager.is_device_disconnected("buggy_motor") == False
    
    def test_safe_device_call_ignores_disconnected_devices(self, device_manager):
        """Test that safe_device_call ignores calls to disconnected devices"""
        motor = MockMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        device_manager.available_devices.append("test_motor")
        
        # Mark as disconnected
        device_manager._disconnected_devices.add("test_motor")
        
        # Should ignore the call
        result = device_manager.safe_device_call("test_motor", "run", 500)
        assert result is None
        assert motor._speed == 0  # Motor should not have been called
    
    def test_enable_port_monitoring(self, device_manager):
        """Test enabling port monitoring"""
        motor = MockMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        device_manager.available_devices.append("test_motor")
        device_manager.device_ports["test_motor"] = str(MockPort.A)
        device_manager._raw_ports["test_motor"] = MockPort.A
        device_manager.device_types["test_motor"] = MockMotor
        
        device_manager.enable_port_monitoring(check_interval=0.1)
        
        assert device_manager._port_monitor is not None
        assert device_manager._port_monitor.is_running()
        
        # Cleanup
        device_manager.disable_port_monitoring()
    
    def test_disable_port_monitoring(self, device_manager):
        """Test disabling port monitoring"""
        device_manager.enable_port_monitoring(check_interval=0.1)
        device_manager.disable_port_monitoring()
        
        assert device_manager._port_monitor is None
    
    def test_device_disconnect_callback(self, device_manager):
        """Test that disconnect callback updates device manager state"""
        motor = MockMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        device_manager.available_devices.append("test_motor")
        device_manager.device_ports["test_motor"] = str(MockPort.A)
        device_manager.device_types["test_motor"] = MockMotor
        
        # Simulate disconnect callback
        status = {'port': str(MockPort.A)}
        device_manager._on_device_disconnect("test_motor", status)
        
        assert "test_motor" in device_manager._disconnected_devices
        assert "test_motor" not in device_manager.available_devices
        assert "test_motor" in device_manager.missing_devices
    
    def test_device_disconnect_preserves_device_reference(self, device_manager):
        """Test that disconnect callback does NOT clear the device reference, but marks it as disconnected
        
        The device reference is preserved to allow automatic reconnection detection.
        is_device_available() checks _disconnected_devices instead of devices[name] being None.
        """
        motor = MockMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        device_manager.available_devices.append("test_motor")
        device_manager.device_ports["test_motor"] = str(MockPort.A)
        device_manager.device_types["test_motor"] = MockMotor
        
        # Initially the device should be available
        assert device_manager.is_device_available("test_motor") == True
        
        # Simulate disconnect callback
        status = {'port': str(MockPort.A)}
        device_manager._on_device_disconnect("test_motor", status)
        
        # After disconnect, is_device_available should return False (via _disconnected_devices)
        assert device_manager.is_device_available("test_motor") == False
        
        # But the device reference should be PRESERVED (not None) for auto-reconnect
        assert device_manager.devices["test_motor"] is not None
        assert device_manager.devices["test_motor"] == motor
        
        # Device should be in _disconnected_devices
        assert "test_motor" in device_manager._disconnected_devices
    
    def test_device_reconnect_callback(self, device_manager):
        """Test that reconnect callback updates device manager state"""
        motor = MockMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        device_manager.missing_devices.append("test_motor")
        device_manager._disconnected_devices.add("test_motor")
        device_manager.device_ports["test_motor"] = str(MockPort.A)
        device_manager.device_types["test_motor"] = MockMotor
        
        # Simulate reconnect callback
        status = {'port': str(MockPort.A)}
        device_manager._on_device_reconnect("test_motor", status)
        
        assert "test_motor" not in device_manager._disconnected_devices
        assert "test_motor" in device_manager.available_devices
        assert "test_motor" not in device_manager.missing_devices
    
    def test_cleanup_stops_port_monitoring(self, device_manager):
        """Test that cleanup stops port monitoring"""
        device_manager.enable_port_monitoring(check_interval=0.1)
        device_manager.cleanup()
        
        assert device_manager._port_monitor is None
    
    def test_get_port_monitor_status(self, device_manager):
        """Test getting port monitor status"""
        # Without monitoring enabled
        assert device_manager.get_port_monitor_status() is None
        
        # With monitoring enabled
        motor = MockMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        device_manager.available_devices.append("test_motor")
        device_manager.device_ports["test_motor"] = str(MockPort.A)
        device_manager._raw_ports["test_motor"] = MockPort.A
        device_manager.device_types["test_motor"] = MockMotor
        
        device_manager.enable_port_monitoring(check_interval=0.1)
        
        status = device_manager.get_port_monitor_status()
        assert status is not None
        assert "test_motor" in status
        
        device_manager.cleanup()
    
    def test_try_init_device_stores_raw_port(self, device_manager):
        """Test that try_init_device stores the actual port object in _raw_ports"""
        # try_init_device should store both the string representation and raw port
        device_manager.try_init_device(MockMotor, MockPort.B, "test_motor")
        
        # Verify both are stored
        assert "test_motor" in device_manager.device_ports
        assert "test_motor" in device_manager._raw_ports
        
        # device_ports should have string, _raw_ports should have actual port object
        assert device_manager.device_ports["test_motor"] == str(MockPort.B)
        assert device_manager._raw_ports["test_motor"] == MockPort.B
    
    def test_enable_port_monitoring_uses_raw_ports(self, device_manager):
        """Test that enable_port_monitoring uses actual port objects from _raw_ports"""
        from ev3_devices.port_monitor import PortMonitor
        
        # Use try_init_device which populates _raw_ports correctly
        device_manager.try_init_device(MockMotor, MockPort.A, "test_motor")
        
        device_manager.enable_port_monitoring(check_interval=0.1)
        
        # Verify the port monitor received the actual port object
        status = device_manager._port_monitor.get_device_status("test_motor")
        assert status is not None
        assert status['port'] == MockPort.A  # Should be actual port, not string
        
        device_manager.cleanup()


class TestPortMonitorReinitialization:
    """Tests for the PortMonitor device reinitialization on reconnect"""
    
    @pytest.fixture
    def device_manager(self):
        """Create a fresh DeviceManager"""
        from ev3_devices import DeviceManager
        return DeviceManager()
    
    @pytest.fixture
    def port_monitor(self, device_manager):
        """Create a PortMonitor instance"""
        from ev3_devices.port_monitor import PortMonitor
        return PortMonitor(device_manager, check_interval=0.1)
    
    def test_health_check_tries_reinitialize_none_device(self, port_monitor, device_manager):
        """Test that _perform_health_check attempts to reinitialize when device is None
        
        This tests the case where a device was None from the start (failed to init at boot),
        not from disconnect (since disconnect no longer sets devices to None).
        """
        # Register a device with the port monitor
        port_monitor.register_device("test_motor", MockMotor, MockPort.A)
        
        # Device is None because it failed to initialize at boot (not from disconnect)
        device_manager.devices["test_motor"] = None
        device_manager.missing_devices.append("test_motor")
        
        # Health check should try to reinitialize and succeed (MockMotor doesn't fail)
        is_healthy = port_monitor._perform_health_check("test_motor")
        
        # Should have reinitialized the device
        assert is_healthy == True
        assert device_manager.devices["test_motor"] is not None
        assert isinstance(device_manager.devices["test_motor"], MockMotor)
    
    def test_health_check_reinit_fails_gracefully(self, port_monitor, device_manager):
        """Test that _perform_health_check handles failed reinitialization gracefully"""
        # Create a device type that always fails to initialize
        class FailingDeviceType:
            def __init__(self, port):
                raise Exception("Device not connected")
        
        # Register a device with the port monitor
        port_monitor.register_device("failing_device", FailingDeviceType, MockPort.A)
        
        # Set device to None
        device_manager.devices["failing_device"] = None
        
        # Health check should fail (reinitialization fails)
        is_healthy = port_monitor._perform_health_check("failing_device")
        
        assert is_healthy == False
        assert device_manager.devices.get("failing_device") is None
    
    def test_reconnect_after_device_set_to_none(self, port_monitor, device_manager):
        """Test full reconnect cycle when device was set to None on disconnect"""
        reconnect_callback = Mock()
        port_monitor.on_reconnect(reconnect_callback)
        
        # Setup: Device exists initially
        motor = MockMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        device_manager.available_devices.append("test_motor")
        device_manager.device_types["test_motor"] = MockMotor
        device_manager._raw_ports["test_motor"] = MockPort.A
        
        port_monitor.register_device("test_motor", MockMotor, MockPort.A)
        
        # Simulate disconnect: device set to None and marked disconnected
        device_manager.devices["test_motor"] = None
        port_monitor._device_status["test_motor"]['connected'] = False
        
        # Run health check - should reinitialize and detect reconnect
        port_monitor._check_device("test_motor")
        
        # Verify reconnect was detected
        assert reconnect_callback.called
        assert port_monitor.is_device_connected("test_motor") == True
        assert device_manager.devices["test_motor"] is not None


class TestDeviceManagerMissingDeviceRegistration:
    """Tests for registering missing devices with port monitor"""
    
    @pytest.fixture
    def device_manager(self):
        """Create a fresh DeviceManager"""
        from ev3_devices import DeviceManager
        return DeviceManager()
    
    def test_enable_port_monitoring_registers_missing_devices(self, device_manager):
        """Test that enable_port_monitoring also registers devices from missing_devices"""
        # Create a device type that will fail initialization (device physically absent)
        class AbsentMotor:
            def __init__(self, port):
                raise Exception("Device not connected - port is empty")
        
        # Setup: One available device
        available_motor = MockMotor(MockPort.A)
        device_manager.devices["available_motor"] = available_motor
        device_manager.available_devices.append("available_motor")
        device_manager.device_ports["available_motor"] = str(MockPort.A)
        device_manager._raw_ports["available_motor"] = MockPort.A
        device_manager.device_types["available_motor"] = MockMotor
        
        # Missing device (failed init at boot) - uses a device type that will keep failing
        device_manager.devices["missing_motor"] = None
        device_manager.missing_devices.append("missing_motor")
        device_manager.device_ports["missing_motor"] = str(MockPort.B)
        device_manager._raw_ports["missing_motor"] = MockPort.B
        device_manager.device_types["missing_motor"] = AbsentMotor  # Will keep failing
        
        # Enable port monitoring
        device_manager.enable_port_monitoring(check_interval=0.1)
        
        # Both devices should be registered in the port monitor
        available_status = device_manager._port_monitor.get_device_status("available_motor")
        missing_status = device_manager._port_monitor.get_device_status("missing_motor")
        
        assert available_status is not None
        assert missing_status is not None
        
        # Available device should show connected
        assert available_status['connected'] == True
        # Missing device should remain not connected (AbsentMotor fails to init)
        assert missing_status['connected'] == False
        
        device_manager.cleanup()
    
    def test_missing_device_can_be_detected_when_plugged_in(self, device_manager):
        """Test that a device missing at boot can be detected when later plugged in"""
        reconnect_callback = Mock()
        
        # Create a controllable device type
        class PluggableMotor:
            is_plugged_in = False  # Class-level: simulates physical plug state
            
            def __init__(self, port):
                if not PluggableMotor.is_plugged_in:
                    raise Exception("Device not connected - port is empty")
                self.port = port
                self._angle = 0
            
            def angle(self):
                return self._angle
            
            def stop(self):
                pass
        
        # Initially device is NOT plugged in
        PluggableMotor.is_plugged_in = False
        device_manager.devices["late_motor"] = None
        device_manager.missing_devices.append("late_motor")
        device_manager.device_ports["late_motor"] = str(MockPort.C)
        device_manager._raw_ports["late_motor"] = MockPort.C
        device_manager.device_types["late_motor"] = PluggableMotor
        
        # Enable port monitoring (callback must be registered BEFORE start)
        device_manager.enable_port_monitoring(check_interval=0.05)
        device_manager._port_monitor.on_reconnect(reconnect_callback)
        
        # Device should still be None (init fails)
        assert device_manager.devices["late_motor"] is None
        
        # Now "plug in" the device
        PluggableMotor.is_plugged_in = True
        
        # Wait for port monitor to attempt reinitialization
        time.sleep(0.15)
        
        # Device should have been reinitialized and reconnect callback called
        assert reconnect_callback.called
        assert device_manager.devices["late_motor"] is not None
        assert device_manager._port_monitor.is_device_connected("late_motor") == True
        
        device_manager.cleanup()


class TestLockOrderInversion:
    """Tests to verify no deadlock between DeviceManager._device_lock and PortMonitor._lock"""
    
    @pytest.fixture
    def device_manager(self):
        """Create a fresh DeviceManager"""
        from ev3_devices import DeviceManager
        return DeviceManager()
    
    def test_try_init_device_does_not_hold_lock_during_register(self, device_manager):
        """Test that try_init_device doesn't hold _device_lock while calling register_device
        
        This prevents lock-order inversion: if callbacks try to acquire _device_lock
        while PortMonitor holds its _lock, and try_init_device holds _device_lock
        while calling register_device (which acquires _lock), we get a deadlock.
        """
        # Enable port monitoring first
        device_manager.enable_port_monitoring(check_interval=1.0)
        
        # This should not deadlock
        device_manager.try_init_device(MockMotor, MockPort.B, "new_motor")
        
        # Verify the device was registered
        assert device_manager.devices.get("new_motor") is not None
        assert device_manager._port_monitor.get_device_status("new_motor") is not None
        
        device_manager.cleanup()
    
    def test_concurrent_device_init_and_monitoring(self, device_manager):
        """Test that concurrent device initialization and monitoring doesn't deadlock"""
        import threading
        
        # Set up some initial devices
        motor = MockMotor(MockPort.A)
        device_manager.devices["motor_a"] = motor
        device_manager.available_devices.append("motor_a")
        device_manager.device_types["motor_a"] = MockMotor
        device_manager._raw_ports["motor_a"] = MockPort.A
        device_manager.device_ports["motor_a"] = str(MockPort.A)
        
        # Enable monitoring with fast checks
        device_manager.enable_port_monitoring(check_interval=0.05)
        
        errors = []
        
        def init_devices():
            """Thread that initializes devices"""
            try:
                for i in range(10):
                    # Create a simple mock class that can be instantiated
                    class TestMotor:
                        def __init__(self, port):
                            self.port = port
                            self._angle = 0
                        def angle(self):
                            return self._angle
                        def stop(self):
                            pass
                    
                    device_manager.try_init_device(TestMotor, MockPort.B, f"test_motor_{i}")
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)
        
        # Start device initialization in a separate thread
        init_thread = threading.Thread(target=init_devices)
        init_thread.start()
        
        # Let it run concurrently with monitoring
        time.sleep(0.3)
        
        # Wait for completion
        init_thread.join(timeout=2.0)
        
        # Should complete without deadlock or errors
        assert not init_thread.is_alive(), "Thread should have completed (no deadlock)"
        assert len(errors) == 0, f"No errors expected, got: {errors}"
        
        device_manager.cleanup()


class TestIsDeviceAvailableWithDisconnectedSet:
    """Tests for is_device_available() checking _disconnected_devices"""
    
    @pytest.fixture
    def device_manager(self):
        """Create a fresh DeviceManager"""
        from ev3_devices import DeviceManager
        return DeviceManager()
    
    def test_is_device_available_returns_false_when_in_disconnected_set(self, device_manager):
        """Test that is_device_available returns False when device is in _disconnected_devices"""
        motor = MockMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        device_manager.available_devices.append("test_motor")
        
        # Initially available
        assert device_manager.is_device_available("test_motor") == True
        
        # Add to disconnected set
        device_manager._disconnected_devices.add("test_motor")
        
        # Should be unavailable even though device reference is not None
        assert device_manager.is_device_available("test_motor") == False
        assert device_manager.devices["test_motor"] is not None  # Reference preserved
    
    def test_is_device_available_after_reconnect(self, device_manager):
        """Test that is_device_available returns True after reconnect callback"""
        motor = MockMotor(MockPort.A)
        device_manager.devices["test_motor"] = motor
        device_manager.available_devices.append("test_motor")
        device_manager.device_types["test_motor"] = MockMotor
        device_manager._raw_ports["test_motor"] = MockPort.A
        device_manager.device_ports["test_motor"] = str(MockPort.A)
        
        # Simulate disconnect
        device_manager._on_device_disconnect("test_motor", {'port': str(MockPort.A)})
        assert device_manager.is_device_available("test_motor") == False
        
        # Simulate reconnect
        device_manager._on_device_reconnect("test_motor", {'port': str(MockPort.A)})
        assert device_manager.is_device_available("test_motor") == True


class TestAutoReconnectWithPreservedReference:
    """Tests for automatic reconnect detection with preserved device reference"""
    
    @pytest.fixture
    def device_manager(self):
        """Create a fresh DeviceManager"""
        from ev3_devices import DeviceManager
        return DeviceManager()
    
    @pytest.fixture
    def port_monitor(self, device_manager):
        """Create a PortMonitor instance"""
        from ev3_devices.port_monitor import PortMonitor
        return PortMonitor(device_manager, check_interval=0.1)
    
    def test_health_check_uses_preserved_reference(self, port_monitor, device_manager):
        """Test that health check works with preserved device reference after disconnect"""
        # Create a controllable motor
        class ControllableMotor:
            should_fail_health_check = False
            
            def __init__(self, port):
                self.port = port
            
            def angle(self):
                if ControllableMotor.should_fail_health_check:
                    raise OSError("Device disconnected")
                return 0
            
            def stop(self):
                pass
        
        motor = ControllableMotor(MockPort.A)
        device_manager.devices["ctrl_motor"] = motor
        device_manager.available_devices.append("ctrl_motor")
        device_manager.device_types["ctrl_motor"] = ControllableMotor
        device_manager._raw_ports["ctrl_motor"] = MockPort.A
        device_manager.device_ports["ctrl_motor"] = str(MockPort.A)
        
        port_monitor.register_device("ctrl_motor", ControllableMotor, MockPort.A)
        
        # Initially healthy
        assert port_monitor._perform_health_check("ctrl_motor") == True
        
        # Simulate disconnect scenario - device still has reference but health check fails
        ControllableMotor.should_fail_health_check = True
        assert port_monitor._perform_health_check("ctrl_motor") == False
        
        # Simulate reconnect - health check passes again
        ControllableMotor.should_fail_health_check = False
        assert port_monitor._perform_health_check("ctrl_motor") == True
    
    def test_reconnect_detected_with_stale_reference(self, device_manager):
        """Test that reconnect is detected even when using the stale device reference
        
        This tests the scenario where:
        1. Device disconnects (reference preserved, added to _disconnected_devices)
        2. Device health check fails
        3. Device reconnects (health check passes)
        4. Reconnect callback removes from _disconnected_devices
        """
        reconnect_callback = Mock()
        
        # Create a controllable motor
        class ControllableMotor:
            health_check_fails = False
            
            def __init__(self, port):
                self.port = port
            
            def angle(self):
                if ControllableMotor.health_check_fails:
                    raise OSError("Device disconnected")
                return 0
            
            def stop(self):
                pass
        
        motor = ControllableMotor(MockPort.A)
        device_manager.devices["ctrl_motor"] = motor
        device_manager.available_devices.append("ctrl_motor")
        device_manager.device_types["ctrl_motor"] = ControllableMotor
        device_manager._raw_ports["ctrl_motor"] = MockPort.A
        device_manager.device_ports["ctrl_motor"] = str(MockPort.A)
        
        # Enable monitoring
        device_manager.enable_port_monitoring(check_interval=0.05)
        device_manager._port_monitor.on_reconnect(reconnect_callback)
        
        # Initially connected
        assert device_manager.is_device_available("ctrl_motor") == True
        
        # Simulate disconnect via callback (reference preserved)
        device_manager._on_device_disconnect("ctrl_motor", {'port': str(MockPort.A)})
        device_manager._port_monitor._device_status["ctrl_motor"]['connected'] = False
        
        # Verify device reference is preserved
        assert device_manager.devices["ctrl_motor"] is motor
        assert device_manager.is_device_available("ctrl_motor") == False
        
        # Health check should fail (simulating disconnected device)
        ControllableMotor.health_check_fails = True
        
        # Wait for a health check
        time.sleep(0.1)
        
        # Simulate reconnect (health check passes)
        ControllableMotor.health_check_fails = False
        
        # Wait for reconnect detection
        time.sleep(0.15)
        
        # Reconnect should have been detected
        assert reconnect_callback.called
        assert device_manager._port_monitor.is_device_connected("ctrl_motor") == True
        
        device_manager.cleanup()


class TestIntegration:
    """Integration tests for the complete disconnect/reconnect flow"""
    
    @pytest.fixture
    def device_manager(self):
        """Create a fresh DeviceManager"""
        from ev3_devices import DeviceManager
        return DeviceManager()
    
    def test_full_disconnect_reconnect_cycle(self, device_manager):
        """Test a complete disconnect and reconnect cycle"""
        # Create a motor that can simulate disconnect/reconnect via class-level flag
        class SimulatedMotor:
            should_fail_init = False  # Class-level flag to control init behavior
            
            def __init__(self, port):
                if SimulatedMotor.should_fail_init:
                    raise Exception("Device not connected")
                self.port = port
                self._speed = 0
                self._angle = 0
                self._fail_health_check = False  # Instance-level flag for health checks
            
            def run(self, speed):
                if self._fail_health_check:
                    raise Exception("Device disconnected")
                self._speed = speed
            
            def angle(self):
                if self._fail_health_check:
                    raise Exception("Device disconnected")
                return self._angle
            
            def stop(self):
                self._speed = 0
        
        # Initially, device connects successfully
        SimulatedMotor.should_fail_init = False
        motor = SimulatedMotor(MockPort.A)
        device_manager.devices["sim_motor"] = motor
        device_manager.available_devices.append("sim_motor")
        device_manager.device_ports["sim_motor"] = str(MockPort.A)
        device_manager._raw_ports["sim_motor"] = MockPort.A
        device_manager.device_types["sim_motor"] = SimulatedMotor
        
        # Enable port monitoring with fast check interval
        device_manager.enable_port_monitoring(check_interval=0.05)
        
        # Verify motor works initially
        result = device_manager.safe_device_call("sim_motor", "run", 500)
        assert motor._speed == 500
        
        # Simulate disconnect: make health checks fail AND prevent reinitialization
        motor._fail_health_check = True
        SimulatedMotor.should_fail_init = True  # Prevent immediate re-init
        
        # Wait for monitoring to detect disconnect
        time.sleep(0.2)
        
        # Verify device is marked as disconnected (or unavailable)
        # Note: with the fix, if reinit fails, device stays disconnected
        assert device_manager.is_device_disconnected("sim_motor") == True or \
               device_manager.devices["sim_motor"] is None
        
        # Commands should now be ignored
        result = device_manager.safe_device_call("sim_motor", "run", 1000)
        assert result is None
        
        # Simulate reconnect by allowing initialization to succeed
        SimulatedMotor.should_fail_init = False
        
        # Wait for monitoring to detect reconnect
        time.sleep(0.2)
        
        # Verify device is no longer marked as disconnected
        assert device_manager.is_device_disconnected("sim_motor") == False
        
        # Get the new motor instance
        new_motor = device_manager.get_device("sim_motor")
        assert new_motor is not None
        
        # Commands should work again after reconnect
        result = device_manager.safe_device_call("sim_motor", "run", 750)
        assert new_motor._speed == 750
        
        # Cleanup
        device_manager.cleanup()
    
    def test_full_disconnect_reconnect_with_preserved_reference(self, device_manager):
        """Test complete disconnect/reconnect cycle where device reference is preserved on disconnect
        
        This tests the fix for P1: the port monitor should successfully detect reconnection
        even when the device reference is preserved (not set to None) during disconnect.
        The is_device_available() method checks _disconnected_devices for availability.
        """
        # Track callbacks
        disconnect_callback = Mock()
        reconnect_callback = Mock()
        
        # Create a device type that can be controlled to fail/succeed
        class ControllableMotor:
            health_check_fails = False  # Class-level flag to control health check behavior
            
            def __init__(self, port):
                self.port = port
                self._speed = 0
                self._angle = 0
            
            def run(self, speed):
                self._speed = speed
            
            def angle(self):
                if ControllableMotor.health_check_fails:
                    raise OSError("Device disconnected")
                return self._angle
            
            def stop(self):
                self._speed = 0
        
        # Initially device is connected
        ControllableMotor.health_check_fails = False
        motor = ControllableMotor(MockPort.A)
        device_manager.devices["ctrl_motor"] = motor
        device_manager.available_devices.append("ctrl_motor")
        device_manager.device_ports["ctrl_motor"] = str(MockPort.A)
        device_manager._raw_ports["ctrl_motor"] = MockPort.A
        device_manager.device_types["ctrl_motor"] = ControllableMotor
        
        # Enable port monitoring
        device_manager.enable_port_monitoring(check_interval=0.05)
        device_manager._port_monitor.on_disconnect(disconnect_callback)
        device_manager._port_monitor.on_reconnect(reconnect_callback)
        
        # Verify motor works initially
        assert device_manager.is_device_available("ctrl_motor") == True
        
        # Simulate disconnect by calling the disconnect callback
        # (In real use, port monitor detects this automatically via health check failure)
        device_manager._on_device_disconnect("ctrl_motor", {'port': str(MockPort.A)})
        device_manager._port_monitor._device_status["ctrl_motor"]['connected'] = False
        
        # Device reference should be PRESERVED but marked as unavailable
        assert device_manager.devices["ctrl_motor"] is motor  # Reference preserved
        assert device_manager.is_device_available("ctrl_motor") == False  # But unavailable
        assert "ctrl_motor" in device_manager._disconnected_devices
        
        # Simulate device being plugged back in (health check will pass)
        ControllableMotor.health_check_fails = False
        
        # Wait for port monitor to detect reconnection
        time.sleep(0.15)
        
        # Device should still be connected and available
        assert device_manager._port_monitor.is_device_connected("ctrl_motor") == True
        assert reconnect_callback.called
        
        device_manager.cleanup()
    
    def test_boot_with_missing_device_then_plug_in(self, device_manager):
        """Test scenario where device is missing at boot but later plugged in
        
        This tests the fix for P2: the port monitor should register missing devices
        and detect when they are later connected.
        """
        reconnect_callback = Mock()
        
        # Create a controllable device type
        class PluggableMotor:
            is_plugged_in = False  # Class-level: simulates physical plug state
            
            def __init__(self, port):
                if not PluggableMotor.is_plugged_in:
                    raise Exception("Device not connected - port is empty")
                self.port = port
                self._angle = 0
            
            def angle(self):
                return self._angle
            
            def stop(self):
                pass
        
        # Initially device is NOT plugged in (simulates boot with missing device)
        PluggableMotor.is_plugged_in = False
        device_manager.devices["boot_missing"] = None
        device_manager.missing_devices.append("boot_missing")
        device_manager.device_ports["boot_missing"] = str(MockPort.D)
        device_manager._raw_ports["boot_missing"] = MockPort.D
        device_manager.device_types["boot_missing"] = PluggableMotor
        
        # Enable port monitoring - should register missing devices too
        device_manager.enable_port_monitoring(check_interval=0.05)
        device_manager._port_monitor.on_reconnect(reconnect_callback)
        
        # Verify device is registered in port monitor but not connected
        status = device_manager._port_monitor.get_device_status("boot_missing")
        assert status is not None
        assert status['connected'] == False  # Should remain disconnected
        
        # Wait a bit to confirm device stays disconnected
        time.sleep(0.1)
        assert device_manager.devices["boot_missing"] is None
        assert device_manager._port_monitor.is_device_connected("boot_missing") == False
        
        # Now "plug in" the device
        PluggableMotor.is_plugged_in = True
        
        # Wait for port monitor to detect and reinitialize
        time.sleep(0.15)
        
        # Device should now be connected
        assert device_manager.devices["boot_missing"] is not None
        assert device_manager._port_monitor.is_device_connected("boot_missing") == True
        assert reconnect_callback.called
        
        device_manager.cleanup()
