#!/usr/bin/env python3

"""
Unit tests for DriveSystem base class
"""

import unittest
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DeviceManager import DeviceManager
from DriveSystem import DriveSystem

class ConcreteDriveSystem(DriveSystem):
    """Concrete implementation of DriveSystem for testing"""
    
    def __init__(self, device_manager):
        super().__init__(device_manager)
        self.move_forward_called = False
        self.move_backward_called = False
        self.turn_left_called = False
        self.turn_right_called = False
        self.move_with_steering_called = False
        self.joystick_control_called = False
        self.stop_called = False
    
    def move_forward(self, distance):
        self.move_forward_called = True
        self.last_distance = distance
    
    def move_backward(self, distance):
        self.move_backward_called = True
        self.last_distance = distance
    
    def turn_left(self, angle):
        self.turn_left_called = True
        self.last_angle = angle
    
    def turn_right(self, angle):
        self.turn_right_called = True
        self.last_angle = angle
    
    def move_with_steering(self, distance, steering):
        self.move_with_steering_called = True
        self.last_distance = distance
        self.last_steering = steering
    
    def joystick_control(self, forward_speed, turn_speed):
        self.joystick_control_called = True
        self.last_forward_speed = forward_speed
        self.last_turn_speed = turn_speed
    
    def stop(self):
        self.stop_called = True

class TestDriveSystem(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.device_manager = DeviceManager()
        self.drive_system = ConcreteDriveSystem(self.device_manager)
    
    def test_initialization(self):
        """Test drive system initialization"""
        self.assertEqual(self.drive_system.device_manager, self.device_manager)
    
    def test_abstract_methods_implemented(self):
        """Test that all abstract methods are implemented in concrete class"""
        # These should not raise NotImplementedError
        self.drive_system.move_forward(100)
        self.assertTrue(self.drive_system.move_forward_called)
        
        self.drive_system.move_backward(100)
        self.assertTrue(self.drive_system.move_backward_called)
        
        self.drive_system.turn_left(90)
        self.assertTrue(self.drive_system.turn_left_called)
        
        self.drive_system.turn_right(90)
        self.assertTrue(self.drive_system.turn_right_called)
        
        self.drive_system.move_with_steering(100, 50)
        self.assertTrue(self.drive_system.move_with_steering_called)
        
        self.drive_system.joystick_control(500, 300)
        self.assertTrue(self.drive_system.joystick_control_called)
        
        self.drive_system.stop()
        self.assertTrue(self.drive_system.stop_called)
    
    def test_move_forward_parameters(self):
        """Test move forward parameters are passed correctly"""
        distance = 1000
        self.drive_system.move_forward(distance)
        self.assertEqual(self.drive_system.last_distance, distance)
    
    def test_move_backward_parameters(self):
        """Test move backward parameters are passed correctly"""
        distance = 500
        self.drive_system.move_backward(distance)
        self.assertEqual(self.drive_system.last_distance, distance)
    
    def test_turn_left_parameters(self):
        """Test turn left parameters are passed correctly"""
        angle = 90
        self.drive_system.turn_left(angle)
        self.assertEqual(self.drive_system.last_angle, angle)
    
    def test_turn_right_parameters(self):
        """Test turn right parameters are passed correctly"""
        angle = 45
        self.drive_system.turn_right(angle)
        self.assertEqual(self.drive_system.last_angle, angle)
    
    def test_move_with_steering_parameters(self):
        """Test move with steering parameters are passed correctly"""
        distance = 1000
        steering = 50
        self.drive_system.move_with_steering(distance, steering)
        self.assertEqual(self.drive_system.last_distance, distance)
        self.assertEqual(self.drive_system.last_steering, steering)
    
    def test_joystick_control_parameters(self):
        """Test joystick control parameters are passed correctly"""
        forward_speed = 500
        turn_speed = -300
        self.drive_system.joystick_control(forward_speed, turn_speed)
        self.assertEqual(self.drive_system.last_forward_speed, forward_speed)
        self.assertEqual(self.drive_system.last_turn_speed, turn_speed)

class IncompleteDriverSystem(DriveSystem):
    """Incomplete implementation to test abstract method enforcement"""
    
    def joystick_control(self, forward_speed, turn_speed):
        """Implement this one method to avoid attribute error"""
        raise NotImplementedError("joystick_control must be implemented")

class TestAbstractMethods(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.device_manager = DeviceManager()
        self.incomplete_system = IncompleteDriverSystem(self.device_manager)
    
    def test_abstract_move_forward_raises_error(self):
        """Test that unimplemented move_forward raises NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self.incomplete_system.move_forward(100)
    
    def test_abstract_move_backward_raises_error(self):
        """Test that unimplemented move_backward raises NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self.incomplete_system.move_backward(100)
    
    def test_abstract_turn_left_raises_error(self):
        """Test that unimplemented turn_left raises NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self.incomplete_system.turn_left(90)
    
    def test_abstract_turn_right_raises_error(self):
        """Test that unimplemented turn_right raises NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self.incomplete_system.turn_right(90)
    
    def test_abstract_move_with_steering_raises_error(self):
        """Test that unimplemented move_with_steering raises NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self.incomplete_system.move_with_steering(100, 50)
    
    def test_abstract_joystick_control_raises_error(self):
        """Test that unimplemented joystick_control raises NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self.incomplete_system.joystick_control(500, 300)
    
    def test_abstract_stop_raises_error(self):
        """Test that unimplemented stop raises NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self.incomplete_system.stop()

if __name__ == '__main__':
    unittest.main() 