#!/usr/bin/env python3

"""
Unit tests for DeviceManager class using pytest
"""

import pytest
from tests.mock_ev3_devices import MockMotor, MockUltrasonicSensor, MockPort
from DeviceManager import DeviceManager

class TestDeviceManager:
    
    @pytest.fixture(autouse=True)
    def setup(self, device_manager):
        """Set up test fixtures"""
        self.device_manager = device_manager
    
    def test_initialization(self):
        """Test device manager initialization"""
        assert len(self.device_manager.devices) == 0
        assert len(self.device_manager.available_devices) == 0
        assert len(self.device_manager.missing_devices) == 0
    
    def test_try_init_device_success(self):
        """Test successful device initialization"""
        device = self.device_manager.try_init_device(MockMotor, MockPort.A, "test_motor")
        
        assert device is not None
        assert isinstance(device, MockMotor)
        assert "test_motor" in self.device_manager.devices
        assert "test_motor" in self.device_manager.available_devices
        assert "test_motor" not in self.device_manager.missing_devices
    
    def test_try_init_device_failure(self):
        """Test device initialization failure"""
        # Create a device class that raises an exception
        class FailingDevice:
            def __init__(self, port):
                raise Exception("Device not found")
        
        device = self.device_manager.try_init_device(FailingDevice, MockPort.A, "failing_device")
        
        assert device is None
        assert self.device_manager.devices["failing_device"] is None
        assert "failing_device" not in self.device_manager.available_devices
        assert "failing_device" in self.device_manager.missing_devices
    
    def test_get_device_existing(self):
        """Test getting an existing device"""
        # First add a device
        self.device_manager.try_init_device(MockMotor, MockPort.A, "test_motor")
        
        device = self.device_manager.get_device("test_motor")
        assert device is not None
        assert isinstance(device, MockMotor)
    
    def test_get_device_non_existing(self):
        """Test getting a non-existing device"""
        device = self.device_manager.get_device("non_existing")
        assert device is None
    
    def test_is_device_available_true(self):
        """Test device availability check for available device"""
        self.device_manager.try_init_device(MockMotor, MockPort.A, "test_motor")
        assert self.device_manager.is_device_available("test_motor") == True
    
    def test_is_device_available_false(self):
        """Test device availability check for unavailable device"""
        assert self.device_manager.is_device_available("non_existing") == False
    
    def test_are_devices_available_all_true(self):
        """Test multiple device availability check when all are available"""
        self.device_manager.try_init_device(MockMotor, MockPort.A, "motor1")
        self.device_manager.try_init_device(MockMotor, MockPort.B, "motor2")
        
        assert self.device_manager.are_devices_available(["motor1", "motor2"]) == True
    
    def test_are_devices_available_some_false(self):
        """Test multiple device availability check when some are missing"""
        self.device_manager.try_init_device(MockMotor, MockPort.A, "motor1")
        
        assert self.device_manager.are_devices_available(["motor1", "non_existing"]) == False
    
    def test_are_devices_available_empty_list(self):
        """Test multiple device availability check with empty list"""
        assert self.device_manager.are_devices_available([]) == True
    
    def test_safe_device_call_existing_method(self):
        """Test safe device call with existing device and method"""
        motor = self.device_manager.try_init_device(MockMotor, MockPort.A, "test_motor")
        
        # Call run method
        result = self.device_manager.safe_device_call("test_motor", "run", 500)
        
        # Verify motor received the command
        assert motor._speed == 500
        # Note: safe_device_call may return None even on success
    
    def test_safe_device_call_non_existing_device(self):
        """Test safe device call with non-existing device"""
        result = self.device_manager.safe_device_call("non_existing", "run", 500)
        assert result is None
    
    def test_safe_device_call_non_existing_method(self):
        """Test safe device call with non-existing method"""
        self.device_manager.try_init_device(MockMotor, MockPort.A, "test_motor")
        
        result = self.device_manager.safe_device_call("test_motor", "non_existing_method")
        assert result is None
    
    def test_safe_device_operation_success(self):
        """Test safe device operation with successful operation"""
        motor = self.device_manager.try_init_device(MockMotor, MockPort.A, "test_motor")
        
        def test_operation(device, speed, duration):
            device.run(speed)
            return f"Operation completed with speed {speed}"
        
        result = self.device_manager.safe_device_operation(
            "test_motor",
            "test_operation",
            test_operation,
            500,
            duration=2
        )
        
        assert result == "Operation completed with speed 500"
        assert motor._speed == 500
    
    def test_safe_device_operation_with_exception(self):
        """Test safe device operation that raises an exception"""
        self.device_manager.try_init_device(MockMotor, MockPort.A, "test_motor")
        
        def failing_operation(device):
            raise Exception("Operation failed")
        
        result = self.device_manager.safe_device_operation(
            "test_motor",
            "failing_operation",
            failing_operation
        )
        
        assert result is None
    
    def test_safe_device_operation_non_existing_device(self):
        """Test safe device operation with non-existing device"""
        def test_operation(device):
            return "Should not be called"
        
        result = self.device_manager.safe_device_operation(
            "non_existing",
            "test_operation",
            test_operation
        )
        
        assert result is None
    
    def test_init_device_with_fallback_success(self):
        """Test device initialization with fallback when main device works"""
        device = self.device_manager.init_device_with_fallback(
            MockMotor,
            MockPort.A,
            "test_motor"
        )
        
        assert device is not None
        assert isinstance(device, MockMotor)
        assert "test_motor" in self.device_manager.available_devices
    
    def test_init_device_with_fallback_uses_fallback(self):
        """Test device initialization uses fallback when main device fails"""
        class FailingDevice:
            def __init__(self, port):
                raise Exception("Device not found")
        
        fallback_device = MockMotor(MockPort.B)
        
        device = self.device_manager.init_device_with_fallback(
            FailingDevice,
            MockPort.A,
            "test_motor",
            fallback_device
        )
        
        assert device == fallback_device
        assert "test_motor" in self.device_manager.available_devices
    
    def test_get_device_summary(self):
        """Test getting device summary"""
        # Add some devices
        self.device_manager.try_init_device(MockMotor, MockPort.A, "motor1")
        self.device_manager.try_init_device(MockUltrasonicSensor, MockPort.S1, "sensor1")
        
        # Try to add a failing device
        class FailingDevice:
            def __init__(self, port):
                raise Exception("Device not found")
        
        self.device_manager.try_init_device(FailingDevice, MockPort.B, "failing_device")
        
        # Test based on what DeviceManager actually provides
        assert len(self.device_manager.devices) == 3
        assert len(self.device_manager.available_devices) == 2
        assert len(self.device_manager.missing_devices) == 1
        assert "motor1" in self.device_manager.available_devices
        assert "sensor1" in self.device_manager.available_devices
        assert "failing_device" in self.device_manager.missing_devices
    
    def test_device_persistence(self):
        """Test that devices persist after operations"""
        # Add some devices
        self.device_manager.try_init_device(MockMotor, MockPort.A, "motor1")
        self.device_manager.try_init_device(MockMotor, MockPort.B, "motor2")
        
        # Devices should still be accessible for status reporting
        assert self.device_manager.get_device("motor1") is not None
        assert self.device_manager.get_device("motor2") is not None

# Tests can be run with: pytest tests/test_device_manager_pytest.py 