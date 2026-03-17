#!/usr/bin/env python3

"""
Mock EV3 devices for unit testing without hardware
"""

class MockMotor:
    """Mock EV3 Motor for testing"""
    
    def __init__(self, port):
        self.port = port
        self._angle = 0
        self._speed = 0
        self._running = False
        self._target_angle = None
        self._target_speed = None
        
    def run(self, speed):
        """Mock run method"""
        self._speed = speed
        self._running = True
        
    def run_target(self, speed, angle, stop_type=None, wait=True):
        """Mock run_target method"""
        self._target_speed = speed
        self._target_angle = angle
        self._angle = angle  # Simulate reaching target
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

class MockSensor:
    """Mock EV3 Sensor for testing"""
    
    def __init__(self, port):
        self.port = port
        self._value = 0
        
    def distance(self):
        """Mock distance method for ultrasonic sensor"""
        return self._value
        
    def color(self):
        """Mock color method for color sensor"""
        return 1  # Default color

class MockUltrasonicSensor(MockSensor):
    """Mock Ultrasonic Sensor"""
    
    def __init__(self, port):
        super().__init__(port)
        self._value = 100  # Default distance in mm

class MockColorSensor(MockSensor):
    """Mock Color Sensor"""
    
    def __init__(self, port):
        super().__init__(port)

class MockTouchSensor(MockSensor):
    """Mock Touch Sensor"""
    
    def __init__(self, port):
        super().__init__(port)
        self._pressed = False
        
    def pressed(self):
        """Mock pressed method"""
        return self._pressed

# Mock Stop types
class MockStop:
    HOLD = "HOLD"
    BRAKE = "BRAKE" 
    COAST = "COAST"

# Mock Direction types
class MockDirection:
    CLOCKWISE = "CLOCKWISE"
    COUNTERCLOCKWISE = "COUNTERCLOCKWISE"

# Mock Port types
class MockPort:
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4" 