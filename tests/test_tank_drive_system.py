#!/usr/bin/env python3

"""
Unit tests for TankDriveSystem class using pytest
"""

import pytest
from TankDriveSystem import TankDriveSystem

class TestTankDriveSystem:
    
    @pytest.fixture(autouse=True)
    def setup(self, device_manager_with_motors):
        """Set up test fixtures"""
        self.device_manager, self.mock_left_motor, self.mock_right_motor = device_manager_with_motors
        self.tank_drive = TankDriveSystem(self.device_manager)
        self.tank_drive.initialize()
    
    def test_initialization(self):
        """Test tank drive system initialization"""
        # Check if the tank drive system has been properly set up
        assert self.tank_drive.steering_sensitivity == 2.0
        assert self.tank_drive.device_manager is not None
    
    def test_joystick_control_stop(self):
        """Test joystick control stops when inputs are zero"""
        self.tank_drive.joystick_control(0, 0)
        
        # Both motors should be stopped (speed = 0)
        # Note: The actual implementation calls stop() method which sets speed to 0
        assert self.mock_left_motor._speed == 0
        assert self.mock_right_motor._speed == 0
    
    def test_joystick_control_forward(self):
        """Test joystick control moves forward"""
        forward_speed = 500
        turn_speed = 0
        
        self.tank_drive.joystick_control(forward_speed, turn_speed)
        
        # Both motors should move at same speed (forward)
        expected_left = -forward_speed  # Negated for motor convention
        expected_right = -forward_speed
        
        assert self.mock_left_motor._speed == expected_left
        assert self.mock_right_motor._speed == expected_right
    
    def test_joystick_control_backward(self):
        """Test joystick control moves backward"""
        forward_speed = -500
        turn_speed = 0
        
        self.tank_drive.joystick_control(forward_speed, turn_speed)
        
        # Both motors should move at same speed (backward)
        expected_left = -forward_speed  # Negated for motor convention (positive)
        expected_right = -forward_speed
        
        assert self.mock_left_motor._speed == expected_left
        assert self.mock_right_motor._speed == expected_right
    
    def test_joystick_control_turn_left(self):
        """Test joystick control turns left"""
        forward_speed = 500
        turn_speed = 300  # Positive turn speed = left turn
        
        self.tank_drive.joystick_control(forward_speed, turn_speed)
        
        # Motors should have different speeds for turning
        assert self.mock_left_motor._speed != self.mock_right_motor._speed
    
    def test_joystick_control_turn_right(self):
        """Test joystick control turns right"""
        forward_speed = 500
        turn_speed = -300  # Negative turn speed = right turn
        
        self.tank_drive.joystick_control(forward_speed, turn_speed)
        
        # Motors should have different speeds for turning
        assert self.mock_left_motor._speed != self.mock_right_motor._speed
    
    def test_move_forward(self):
        """Test move forward method"""
        self.tank_drive.move_forward(1000)
        
        # Both motors should run forward (implementation uses negative speeds for forward)
        assert self.mock_left_motor._speed < 0  # Negative = forward in this implementation
        assert self.mock_right_motor._speed < 0
        assert self.mock_left_motor._running == True
        assert self.mock_right_motor._running == True
    
    def test_move_backward(self):
        """Test move backward method"""
        self.tank_drive.move_backward(1000)
        
        # Both motors should run backward (implementation uses positive speeds for backward)
        assert self.mock_left_motor._speed > 0  # Positive = backward in this implementation
        assert self.mock_right_motor._speed > 0
        assert self.mock_left_motor._running == True
        assert self.mock_right_motor._running == True
    
    def test_turn_left(self):
        """Test turn left method"""
        self.tank_drive.turn_left(90)
        
        # Check that motors are moving (actual speeds depend on implementation)
        # Both motors should be running for counter-rotation
        assert self.mock_left_motor._running == True
        assert self.mock_right_motor._running == True
        # Motors should have different speeds for turning
        assert self.mock_left_motor._speed != self.mock_right_motor._speed
    
    def test_turn_right(self):
        """Test turn right method"""
        self.tank_drive.turn_right(90)
        
        # Check that motors are moving (actual speeds depend on implementation)
        # Both motors should be running for counter-rotation
        assert self.mock_left_motor._running == True
        assert self.mock_right_motor._running == True
        # Motors should have different speeds for turning
        assert self.mock_left_motor._speed != self.mock_right_motor._speed
    
    def test_stop(self):
        """Test stop method"""
        # First start moving
        self.tank_drive.move_forward(1000)
        
        # Then stop
        self.tank_drive.stop()
        
        # Both motors should be stopped
        assert self.mock_left_motor._speed == 0
        assert self.mock_right_motor._speed == 0
        assert self.mock_left_motor._running == False
        assert self.mock_right_motor._running == False
    
    def test_set_motor_speeds(self):
        """Test set motor speeds method"""
        left_speed = 300
        right_speed = 400
        
        self.tank_drive.set_motor_speeds(left_speed, right_speed)
        
        assert self.mock_left_motor._speed == left_speed
        assert self.mock_right_motor._speed == right_speed
    
    def test_move_with_steering(self):
        """Test move with steering method"""
        distance = 1000
        steering = 500  # Positive steering for left turn
        
        self.tank_drive.move_with_steering(distance, steering)
        
        # Should result in differential motor speeds
        assert self.mock_left_motor._speed != self.mock_right_motor._speed
    
    def test_set_steering_sensitivity(self):
        """Test setting steering sensitivity"""
        new_sensitivity = 3.0
        self.tank_drive.set_steering_sensitivity(new_sensitivity)
        assert self.tank_drive.steering_sensitivity == new_sensitivity
    
    def test_drift_left(self):
        """Test drift left method"""
        self.tank_drive.drift_left(500)
        
        # Both motors should be running but at different speeds for drift
        assert self.mock_left_motor._running == True
        assert self.mock_right_motor._running == True
        # Different speeds create the drift effect
        assert self.mock_left_motor._speed != self.mock_right_motor._speed
    
    def test_drift_right(self):
        """Test drift right method"""
        self.tank_drive.drift_right(500)
        
        # Both motors should be running but at different speeds for drift
        assert self.mock_left_motor._running == True
        assert self.mock_right_motor._running == True
        # Different speeds create the drift effect
        assert self.mock_left_motor._speed != self.mock_right_motor._speed
    
    def test_speed_validation(self):
        """Test speed validation and clamping"""
        # Test with extreme speeds
        extreme_speed = 2000  # Above typical max
        self.tank_drive.joystick_control(extreme_speed, 0)
        
        # Speeds should be reasonable (implementation specific)
        assert abs(self.mock_left_motor._speed) <= 1000
        assert abs(self.mock_right_motor._speed) <= 1000
    
    def test_without_motors(self, device_manager):
        """Test tank drive system without motors available"""
        # Create tank drive with empty device manager (no motors added)
        tank_drive_no_motors = TankDriveSystem(device_manager)
        tank_drive_no_motors.initialize()
        
        # Should not raise exceptions
        tank_drive_no_motors.joystick_control(500, 0)
        tank_drive_no_motors.stop()
        tank_drive_no_motors.move_forward(1000)

# Tests can be run with: pytest tests/test_tank_drive_system.py 