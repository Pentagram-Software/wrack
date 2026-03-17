#!/usr/bin/env python3

"""
Unit tests for PS4Controller class using pytest
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open
import threading
from time import sleep
import struct
import os

from robot_controllers import PS4Controller, MIN_JOYSTICK_MOVE

class TestPS4Controller:
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures"""
        self.controller = PS4Controller()
        
        # Track callback calls
        self.callback_calls = []
        self.callback_args = []
        
        # Mock file operations to avoid actual hardware access
        self.mock_files = {}
    
    def test_initialization(self):
        """Test controller initialization"""
        assert self.controller.stopped == False
        assert self.controller.connected == False
        assert self.controller.l_left == 0
        assert self.controller.l_forward == 0
        assert self.controller.r_left == 0
        assert self.controller.r_forward == 0
        assert self.controller.last_joystick_event_time == 0
    
    def test_inheritance_from_event_handler(self):
        """Test that PS4Controller properly inherits from EventHandler"""
        from event_handler import EventHandler
        assert isinstance(self.controller, EventHandler)
        
        # Test that EventHandler methods are available
        assert hasattr(self.controller, 'on')
        assert hasattr(self.controller, 'trigger')
        assert hasattr(self.controller, 'callbacks')
    
    def test_inheritance_from_threading_thread(self):
        """Test that PS4Controller properly inherits from threading.Thread"""
        assert isinstance(self.controller, threading.Thread)
        
        # Test that Thread methods are available
        assert hasattr(self.controller, 'start')
        assert hasattr(self.controller, 'join')
        assert hasattr(self.controller, 'is_alive')
    
    def test_min_joystick_move_constant(self):
        """Test MIN_JOYSTICK_MOVE constant"""
        assert MIN_JOYSTICK_MOVE == 100
    
    def test_event_constants(self):
        """Test that event constants are defined"""
        from robot_controllers.ps4_controller import (
            EV_SYN, EV_KEY, EV_ABS,
            X_BUTTON, CIRCLE_BUTTON, TRIANGLE_BUTTON, SQUARE_BUTTON,
            LEFT_STICK_X, LEFT_STICK_Y, RIGHT_STICK_X, RIGHT_STICK_Y
        )
        
        assert EV_SYN == 0
        assert EV_KEY == 1
        assert EV_ABS == 3
        assert X_BUTTON == 304
        assert CIRCLE_BUTTON == 305
        assert TRIANGLE_BUTTON == 307
        assert SQUARE_BUTTON == 308
        assert LEFT_STICK_X == 0
        assert LEFT_STICK_Y == 1
        assert RIGHT_STICK_X == 3
        assert RIGHT_STICK_Y == 4
    
    def test_callback_registration_methods(self):
        """Test callback registration methods"""
        def test_callback(sender):
            self.callback_calls.append("test")
        
        # Test various callback registration methods exist
        assert hasattr(self.controller, 'onLeftJoystickMove')
        assert hasattr(self.controller, 'onRightJoystickMove')
        assert hasattr(self.controller, 'onCrossButton')
        assert hasattr(self.controller, 'onOptionsButton')
        
        # Test callback registration
        self.controller.onCrossButton(test_callback)
        
        # Verify callback was registered
        assert self.controller.callbacks is not None
        assert "cross_button" in self.controller.callbacks
        assert test_callback in self.controller.callbacks["cross_button"]
    
    def test_multiple_callback_registrations(self):
        """Test multiple callback registrations"""
        def callback1(sender):
            self.callback_calls.append("callback1")
        
        def callback2(sender):
            self.callback_calls.append("callback2")
        
        self.controller.onCrossButton(callback1)
        self.controller.onCrossButton(callback2)
        
        # Verify both callbacks were registered
        assert len(self.controller.callbacks["cross_button"]) == 2
        assert callback1 in self.controller.callbacks["cross_button"]
        assert callback2 in self.controller.callbacks["cross_button"]
    
    def test_joystick_callback_registration(self):
        """Test joystick callback registration"""
        def joystick_callback(sender):
            self.callback_calls.append("joystick")
            self.callback_args.append({
                'l_left': sender.l_left,
                'l_forward': sender.l_forward,
                'r_left': sender.r_left,
                'r_forward': sender.r_forward
            })
        
        self.controller.onLeftJoystickMove(joystick_callback)
        self.controller.onRightJoystickMove(joystick_callback)
        
        # Verify callbacks were registered
        assert "left_joystick" in self.controller.callbacks
        assert "right_joystick" in self.controller.callbacks
    
    def test_device_path_handling(self):
        """Test device path handling logic"""
        # PS4Controller automatically handles device detection in run() method
        # Test that the logic for finding controller paths exists
        assert hasattr(self.controller, 'run')
        
        # Should have expected device paths in the implementation
        # This is integration-level testing - actual device detection happens at runtime
    
    def test_is_connected_initially_false(self):
        """Test is_connected returns False initially"""
        assert self.controller.is_connected() == False
    
    def test_connection_status_can_change(self):
        """Test that connection status can be updated"""
        # Initially disconnected
        assert self.controller.is_connected() == False
        
        # Can be set to connected (simulating successful device detection)
        self.controller.connected = True
        assert self.controller.is_connected() == True
    
    def test_stop_method(self):
        """Test stop method sets stopped flag"""
        assert self.controller.stopped == False
        
        self.controller.stop()
        
        assert self.controller.stopped == True
    
    def test_manual_event_triggering(self):
        """Test manually triggering events"""
        def test_callback(sender):
            self.callback_calls.append("manual_trigger")
            self.callback_args.append(sender)
        
        self.controller.onCrossButton(test_callback)
        self.controller.trigger("cross_button")
        
        assert len(self.callback_calls) == 1
        assert self.callback_calls[0] == "manual_trigger"
        assert self.callback_args[0] == self.controller
    
    def test_joystick_value_updates(self):
        """Test that joystick values can be updated"""
        # Initially zero
        assert self.controller.l_left == 0
        assert self.controller.l_forward == 0
        
        # Update values (simulating controller input processing)
        self.controller.l_left = 500
        self.controller.l_forward = -300
        
        assert self.controller.l_left == 500
        assert self.controller.l_forward == -300
    
    @pytest.mark.parametrize("event_name,callback_method", [
        ("cross_button", "onCrossButton"),
        ("left_joystick", "onLeftJoystickMove"),
        ("right_joystick", "onRightJoystickMove"),
        ("options_button", "onOptionsButton"),
    ])
    def test_callback_method_exists(self, event_name, callback_method):
        """Test that callback registration methods exist"""
        assert hasattr(self.controller, callback_method)
        
        # Test that the method is callable
        method = getattr(self.controller, callback_method)
        assert callable(method)
    
    def test_event_throttling_attribute(self):
        """Test that event throttling attribute exists"""
        assert hasattr(self.controller, 'last_joystick_event_time')
        assert isinstance(self.controller.last_joystick_event_time, (int, float))
    
    def test_print_debug_function_exists(self):
        """Test that printIn debug function exists"""
        from robot_controllers.ps4_controller import printIn
        
        # Should not raise exception when called
        printIn(1, 1, "test")
    
    def test_error_reporting_integration(self):
        """Test that error reporting is properly integrated"""
        # Verify error reporting imports are available
        from robot_controllers.ps4_controller import report_controller_error, report_exception
        
        assert callable(report_controller_error)
        assert callable(report_exception)
    
    def test_struct_operations(self):
        """Test struct operations for binary data parsing"""
        # Test that struct is available for binary parsing
        import struct
        
        # Simulate parsing a controller event (24 bytes)
        test_data = b'\x00' * 24
        
        # Should be able to unpack binary data (this is how controller events are parsed)
        try:
            unpacked = struct.unpack('llHHI', test_data)
            assert len(unpacked) == 5
        except struct.error:
            # Expected for invalid test data, but struct should be available
            pass
    
    def test_threading_integration(self):
        """Test threading integration"""
        # Controller should be a proper thread
        assert hasattr(self.controller, 'run')
        assert hasattr(self.controller, 'start')
        assert hasattr(self.controller, 'join')
        
        # Should be able to check if alive
        assert hasattr(self.controller, 'is_alive')
        assert not self.controller.is_alive()  # Not started yet
    
    def test_math_operations(self):
        """Test math operations are available (used for joystick calculations)"""
        import math
        
        # Math should be available for controller calculations
        assert hasattr(math, 'sqrt')
        assert hasattr(math, 'atan2')
        
        # Test basic math operations that might be used
        result = math.sqrt(100)
        assert result == 10.0

# Tests can be run with: pytest tests/test_ps4_controller.py