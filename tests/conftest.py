#!/usr/bin/env python3

"""
Pytest configuration and shared fixtures for EV3 PS4 Controlled Robot tests
"""

import pytest
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mock_ev3_devices import MockMotor, MockPort, MockStop, MockDirection, MockUltrasonicSensor

# Mock the pybricks imports globally for all tests BEFORE importing ev3_devices
sys.modules['pybricks'] = type('MockModule', (), {})()
sys.modules['pybricks.ev3devices'] = type('MockModule', (), {
    'Motor': MockMotor,
    'UltrasonicSensor': MockUltrasonicSensor,
    'GyroSensor': type('MockGyroSensor', (), {}),
})()

sys.modules['pybricks.parameters'] = type('MockModule', (), {
    'Port': MockPort,
    'Stop': MockStop,
    'Direction': MockDirection,
})()

sys.modules['pybricks.tools'] = type('MockModule', (), {
    'wait': lambda x: None,
})()

sys.modules['pybricks.hubs'] = type('MockModule', (), {
    'EV3Brick': type('MockEV3Brick', (), {
        'speaker': type('MockSpeaker', (), {
            'say': lambda text: print(f"EV3 Says: {text}")
        })()
    })
})()

# Now import ev3_devices after mocking pybricks
from ev3_devices import DeviceManager

@pytest.fixture
def device_manager():
    """Provide a fresh DeviceManager instance for each test"""
    return DeviceManager()

@pytest.fixture
def mock_motor():
    """Provide a mock motor for testing"""
    return MockMotor(MockPort.A)

@pytest.fixture
def mock_turret_motor():
    """Provide a mock turret motor for testing"""
    return MockMotor(MockPort.C)

@pytest.fixture
def device_manager_with_motors(device_manager):
    """Provide a DeviceManager with mock motors already set up"""
    left_motor = MockMotor(MockPort.A)
    right_motor = MockMotor(MockPort.D)
    
    device_manager.devices["drive_L_motor"] = left_motor
    device_manager.devices["drive_R_motor"] = right_motor
    device_manager.available_devices.extend(["drive_L_motor", "drive_R_motor"])
    
    return device_manager, left_motor, right_motor

@pytest.fixture
def device_manager_with_turret(device_manager):
    """Provide a DeviceManager with mock turret motor"""
    turret_motor = MockMotor(MockPort.C)
    
    device_manager.devices["turret_motor"] = turret_motor
    device_manager.available_devices.append("turret_motor")
    
    return device_manager, turret_motor

@pytest.fixture  
def device_manager_empty():
    """Provide an empty DeviceManager without any devices for testing missing device scenarios"""
    return DeviceManager() 