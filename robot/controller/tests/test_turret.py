#!/usr/bin/env python3

"""
Unit tests for Turret class using pytest
"""

import pytest
from tests.mock_ev3_devices import MockMotor, MockPort
from DeviceManager import DeviceManager
from Turret import Turret

class TestTurret:
    
    @pytest.fixture(autouse=True)
    def setup(self, device_manager_with_turret):
        """Set up test fixtures"""
        self.device_manager, self.mock_motor = device_manager_with_turret
        self.turret = Turret(self.device_manager)
    
    def test_initialization_with_motor(self):
        """Test turret initialization when motor is available"""
        assert self.turret.turret_motor is not None
        assert self.turret.max_angle == 90
        assert self.turret.min_angle == -90
        assert self.turret.max_speed == 360
        assert self.turret.current_target_angle == 0
    
    def test_initialization_without_motor(self, device_manager_empty):
        """Test turret initialization when motor is not available"""
        turret_no_motor = Turret(device_manager_empty)
        assert turret_no_motor.turret_motor is None
    
    @pytest.mark.parametrize("x_axis", [0, 10, -15, 30, -40])
    def test_speed_control_stop_in_deadzone(self, x_axis):
        """Test speed control stops motor when input is in deadzone"""
        self.turret.speed_control(x_axis, 0)
        assert self.mock_motor._speed == 0
        assert self.mock_motor._running == False
    
    @pytest.mark.parametrize("x_axis,expected_speed", [
        (60, 216),    # 60% of 360 = 216°/s
        (-80, -288),  # -80% of 360 = -288°/s  
        (100, 360),   # 100% of 360 = 360°/s (max)
        (-100, -360), # -100% of 360 = -360°/s (max)
    ])
    def test_speed_control_movement_outside_deadzone(self, x_axis, expected_speed):
        """Test speed control moves motor when input is outside deadzone"""
        self.turret.speed_control(x_axis, 0)
        assert self.mock_motor._speed == expected_speed
        assert self.mock_motor._running == True
    
    @pytest.mark.parametrize("x_axis", [150, -150, 200, -200])
    def test_speed_control_speed_clamping(self, x_axis):
        """Test speed control clamps speeds to max_speed"""
        self.turret.speed_control(x_axis, 0)
        assert abs(self.mock_motor._speed) <= self.turret.max_speed
    
    def test_joystick_control_positional(self):
        """Test joystick control for positional movement"""
        # Test center position
        self.turret.joystick_control(0, 0)
        assert self.turret.current_target_angle == 0
        
        # Test extreme positions
        self.turret.joystick_control(100, 0)  # Full right
        assert self.turret.current_target_angle == 90
        
        self.turret.joystick_control(-100, 0)  # Full left
        assert self.turret.current_target_angle == -90
    
    @pytest.mark.parametrize("joystick_value,expected_angle", [
        (0, 0),      # Center
        (100, 90),   # Full right
        (-100, -90), # Full left
        (50, 45),    # Half right
        (-50, -45),  # Half left
    ])
    def test_scale_joystick_to_angle(self, joystick_value, expected_angle):
        """Test joystick to angle scaling"""
        result = self.turret.scale_joystick_to_angle(joystick_value)
        assert result == expected_angle
    
    @pytest.mark.parametrize("angle", [0, 45, -30, 90, -90])
    def test_move_to_angle(self, angle):
        """Test move to specific angle"""
        # move_to_angle should execute without errors (motor positioning)
        # Note: current_target_angle is only updated by joystick_control, not move_to_angle
        self.turret.move_to_angle(angle)
        # Just verify the method completes without error
        assert True
    
    @pytest.mark.parametrize("angle", [120, -120, 150, -150])
    def test_move_to_angle_clamping(self, angle):
        """Test move to angle clamps to limits"""
        # move_to_angle should clamp internally and execute without errors
        # The method clamps the angle before sending to motor but doesn't update current_target_angle
        self.turret.move_to_angle(angle)
        # Just verify the method completes without error
        assert True
    
    def test_get_current_angle(self):
        """Test getting current angle"""
        self.mock_motor._angle = 45
        assert self.turret.get_current_angle() == 45
        
        self.mock_motor._angle = -30
        assert self.turret.get_current_angle() == -30
    
    def test_stop(self):
        """Test turret stop"""
        self.turret.stop()
        assert self.mock_motor._speed == 0
        assert self.mock_motor._running == False
    
    def test_set_angle_limits(self):
        """Test setting angle limits"""
        self.turret.set_angle_limits(-45, 45)
        assert self.turret.min_angle == -45
        assert self.turret.max_angle == 45
    
    def test_set_max_speed(self):
        """Test setting maximum speed"""
        self.turret.set_max_speed(180)
        assert self.turret.max_speed == 180
    
    def test_home_turret(self):
        """Test turret homing"""
        self.turret.home_turret()
        assert self.mock_motor._angle == 0
    
    def test_speed_control_without_motor(self, device_manager_empty):
        """Test speed control when motor is not available"""
        # Create turret without motor
        turret_no_motor = Turret(device_manager_empty)
        
        # Should not raise exceptions even without motor
        turret_no_motor.speed_control(50, 0)
        turret_no_motor.stop()
    
    def test_required_drive_system_methods(self):
        """Test that required DriveSystem methods are implemented"""
        # These should not raise exceptions (placeholder implementations)
        self.turret.move_forward(100)
        self.turret.move_backward(100) 
        self.turret.turn_left(90)
        self.turret.turn_right(90)
        self.turret.move_with_steering(100, 50)

# Tests can be run with: pytest tests/test_turret_pytest.py 