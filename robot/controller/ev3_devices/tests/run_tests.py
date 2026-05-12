#!/usr/bin/env python3

"""
Test runner for ev3_devices tests.

This script sets up the pybricks mocks before running pytest,
which is necessary because the ev3_devices module imports pybricks
at module load time.
"""

import sys
import os

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ============================================================================
# Define all mock classes BEFORE any imports from ev3_devices
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
        self._speed = speed
        self._running = True
        
    def run_target(self, speed, angle, stop_type=None, wait=True):
        self._target_speed = speed
        self._target_angle = angle
        self._angle = angle
        self._running = False
        
    def stop(self, stop_type=None):
        self._speed = 0
        self._running = False
        
    def reset_angle(self, angle=0):
        self._angle = angle
        
    def angle(self):
        return self._angle
        
    def speed(self):
        return self._speed
    
    def stalled(self):
        return self._stalled

class MockUltrasonicSensor:
    """Mock Ultrasonic Sensor"""
    
    def __init__(self, port):
        self.port = port
        self._value = 100
    
    def distance(self):
        return self._value

class MockGyroSensor:
    """Mock Gyro Sensor"""
    
    def __init__(self, port):
        self.port = port
        self._angle = 0
        self._speed = 0
    
    def angle(self):
        return self._angle
    
    def speed(self):
        return self._speed

class MockTouchSensor:
    """Mock Touch Sensor"""
    
    def __init__(self, port):
        self.port = port
        self._pressed = False
    
    def pressed(self):
        return self._pressed

class MockColorSensor:
    """Mock Color Sensor"""
    
    def __init__(self, port):
        self.port = port
    
    def color(self):
        return 1

class MockInfraredSensor:
    """Mock Infrared Sensor"""
    
    def __init__(self, port):
        self.port = port

# ============================================================================
# Set up pybricks module mocks BEFORE importing anything else
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

# Export mock classes for tests to use
__all__ = ['MockMotor', 'MockUltrasonicSensor', 'MockGyroSensor', 'MockPort', 'MockStop', 'MockDirection']

# ============================================================================
# Run pytest
# ============================================================================

if __name__ == '__main__':
    import pytest
    
    # Get the directory containing this script
    test_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Run pytest with the test directory
    sys.exit(pytest.main([
        test_dir,
        '-v',
        '--tb=short',
        '--no-cov',
        '-p', 'no:cacheprovider',  # Disable cache to avoid issues
    ] + sys.argv[1:]))
