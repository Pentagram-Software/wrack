#!/usr/bin/env python3

"""
Pytest configuration and shared fixtures for ev3_devices tests

IMPORTANT: This file sets up mock pybricks modules BEFORE any ev3_devices imports.
The mocks must be defined inline here, not imported from mock_ev3_devices.py,
because importing from that file would trigger ev3_devices.__init__.py to load.
"""

import pytest
import sys
import os

# Add parent directories to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ============================================================================
# Define all mock classes INLINE before any imports from ev3_devices
# ============================================================================

class MockPort:
    """Mock EV3 Port for testing"""
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"

class MockStop:
    """Mock EV3 Stop types for testing"""
    HOLD = "HOLD"
    BRAKE = "BRAKE"
    COAST = "COAST"

class MockDirection:
    """Mock EV3 Direction types for testing"""
    CLOCKWISE = "CLOCKWISE"
    COUNTERCLOCKWISE = "COUNTERCLOCKWISE"

class MockMotor:
    """Mock EV3 Motor for testing"""
    
    def __init__(self, port):
        self.port = port
        self._angle = 0
        self._speed = 0
        self._running = False
        self._target_angle = None
        self._target_speed = None
        self._stalled = False
        
    def run(self, speed):
        """Mock run method"""
        self._speed = speed
        self._running = True
        
    def run_target(self, speed, angle, stop_type=None, wait=True):
        """Mock run_target method"""
        self._target_speed = speed
        self._target_angle = angle
        self._angle = angle
        self._running = False
        
    def stop(self, stop_type=None):
        """Mock stop method"""
        self._speed = 0
        self._running = False
        
    def reset_angle(self, angle=0):
        """Mock reset_angle method"""
        self._angle = angle
        
    def angle(self):
        """Mock angle method"""
        return self._angle
        
    def speed(self):
        """Mock speed method"""
        return self._speed
    
    def stalled(self):
        """Mock stalled method"""
        return self._stalled

class MockUltrasonicSensor:
    """Mock Ultrasonic Sensor"""
    
    def __init__(self, port):
        self.port = port
        self._value = 100
    
    def distance(self):
        """Mock distance method"""
        return self._value

class MockGyroSensor:
    """Mock Gyro Sensor"""
    
    def __init__(self, port):
        self.port = port
        self._angle = 0
        self._speed = 0
    
    def angle(self):
        """Mock angle method"""
        return self._angle
    
    def speed(self):
        """Mock speed method"""
        return self._speed

class MockTouchSensor:
    """Mock Touch Sensor"""
    
    def __init__(self, port):
        self.port = port
        self._pressed = False
    
    def pressed(self):
        """Mock pressed method"""
        return self._pressed

class MockColorSensor:
    """Mock Color Sensor"""
    
    def __init__(self, port):
        self.port = port
    
    def color(self):
        """Mock color method"""
        return 1

class MockInfraredSensor:
    """Mock Infrared Sensor"""
    
    def __init__(self, port):
        self.port = port

# ============================================================================
# Set up pybricks module mocks BEFORE importing ev3_devices
# ============================================================================

mock_pybricks = type('MockModule', (), {})()
mock_ev3devices = type('MockModule', (), {
    'Motor': MockMotor,
    'UltrasonicSensor': MockUltrasonicSensor,
    'GyroSensor': MockGyroSensor,
    'TouchSensor': MockTouchSensor,
    'ColorSensor': MockColorSensor,
    'InfraredSensor': MockInfraredSensor,
})()

mock_parameters = type('MockModule', (), {
    'Port': MockPort,
    'Stop': MockStop,
    'Direction': MockDirection,
    'Button': type('MockButton', (), {})(),
    'Color': type('MockColor', (), {})(),
    'SoundFile': type('MockSoundFile', (), {})(),
    'ImageFile': type('MockImageFile', (), {})(),
    'Align': type('MockAlign', (), {})(),
})()

mock_tools = type('MockModule', (), {
    'wait': lambda x: None,
})()

mock_hubs = type('MockModule', (), {
    'EV3Brick': type('MockEV3Brick', (), {
        'speaker': type('MockSpeaker', (), {
            'say': lambda self, text: print("EV3 Says: {}".format(text)),
            'beep': lambda self, frequency=800, duration=200: None,
        })(),
        'battery': type('MockBattery', (), {
            'voltage': lambda self: 7500,
            'current': lambda self: 500,
        })(),
    })
})()

sys.modules['pybricks'] = mock_pybricks
sys.modules['pybricks.ev3devices'] = mock_ev3devices
sys.modules['pybricks.parameters'] = mock_parameters
sys.modules['pybricks.tools'] = mock_tools
sys.modules['pybricks.hubs'] = mock_hubs

# ============================================================================
# Now it's safe to import ev3_devices
# ============================================================================

from ev3_devices import DeviceManager

# ============================================================================
# Pytest fixtures
# ============================================================================

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
    device_manager.device_ports["drive_L_motor"] = str(MockPort.A)
    device_manager.device_ports["drive_R_motor"] = str(MockPort.D)
    device_manager.device_types["drive_L_motor"] = MockMotor
    device_manager.device_types["drive_R_motor"] = MockMotor
    
    return device_manager, left_motor, right_motor

@pytest.fixture
def device_manager_with_turret(device_manager):
    """Provide a DeviceManager with mock turret motor"""
    turret_motor = MockMotor(MockPort.C)
    
    device_manager.devices["turret_motor"] = turret_motor
    device_manager.available_devices.append("turret_motor")
    device_manager.device_ports["turret_motor"] = str(MockPort.C)
    device_manager.device_types["turret_motor"] = MockMotor
    
    return device_manager, turret_motor

@pytest.fixture  
def device_manager_empty():
    """Provide an empty DeviceManager without any devices for testing missing device scenarios"""
    return DeviceManager()

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
    device_manager.device_ports["drive_L_motor"] = str(MockPort.A)
    device_manager.device_ports["drive_R_motor"] = str(MockPort.D)
    device_manager.device_types["drive_L_motor"] = MockMotor
    device_manager.device_types["drive_R_motor"] = MockMotor
    
    return device_manager, left_motor, right_motor

@pytest.fixture
def device_manager_with_turret(device_manager):
    """Provide a DeviceManager with mock turret motor"""
    turret_motor = MockMotor(MockPort.C)
    
    device_manager.devices["turret_motor"] = turret_motor
    device_manager.available_devices.append("turret_motor")
    device_manager.device_ports["turret_motor"] = str(MockPort.C)
    device_manager.device_types["turret_motor"] = MockMotor
    
    return device_manager, turret_motor

@pytest.fixture  
def device_manager_empty():
    """Provide an empty DeviceManager without any devices for testing missing device scenarios"""
    return DeviceManager()
