#!/usr/bin/env python3

"""
Unit tests for PS4Controller class (supports PS4 DualShock 4 and PS5 DualSense).
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open
import threading
from time import sleep
import struct
import os

from robot_controllers import PS4Controller, MIN_JOYSTICK_MOVE, wait_for_connection


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
        """Test that event constants are defined with correct values"""
        from robot_controllers.ps4_controller import (
            EV_SYN, EV_KEY, EV_ABS,
            X_BUTTON, CIRCLE_BUTTON, TRIANGLE_BUTTON, SQUARE_BUTTON,
            LEFT_STICK_X, LEFT_STICK_Y, RIGHT_STICK_X, RIGHT_STICK_Y,
            L2_TRIGGER, R2_TRIGGER,
        )
        
        assert EV_SYN == 0
        assert EV_KEY == 1
        assert EV_ABS == 3

        # Action buttons — same codes for PS4 and PS5
        assert X_BUTTON == 304        # BTN_SOUTH
        assert CIRCLE_BUTTON == 305   # BTN_EAST
        assert TRIANGLE_BUTTON == 307 # BTN_NORTH
        assert SQUARE_BUTTON == 308   # BTN_WEST

        # Analog axes
        assert LEFT_STICK_X == 0     # ABS_X
        assert LEFT_STICK_Y == 1     # ABS_Y
        assert L2_TRIGGER == 2       # ABS_Z
        assert RIGHT_STICK_X == 3    # ABS_RX
        assert RIGHT_STICK_Y == 4    # ABS_RY
        assert R2_TRIGGER == 5       # ABS_RZ
    
    def test_known_controller_names_contains_ps4_and_ps5(self):
        """Test that KNOWN_CONTROLLER_NAMES includes both PS4 and PS5 device names"""
        from robot_controllers.ps4_controller import KNOWN_CONTROLLER_NAMES

        ps5_names = [n for n in KNOWN_CONTROLLER_NAMES if "DualSense" in n or "dualsense" in n.lower()]
        assert len(ps5_names) >= 1, "KNOWN_CONTROLLER_NAMES must contain at least one PS5 name"

        ps4_names = [n for n in KNOWN_CONTROLLER_NAMES if "Wireless Controller" in n]
        assert len(ps4_names) >= 1, "KNOWN_CONTROLLER_NAMES must contain at least one PS4 name"
    
    def test_find_controller_device_returns_none_when_proc_missing(self):
        """find_controller_device() returns None gracefully when /proc/bus/input/devices is absent"""
        from robot_controllers.ps4_controller import find_controller_device

        with patch("builtins.open", side_effect=FileNotFoundError("no proc")):
            result = find_controller_device()
        assert result is None
    
    def test_find_controller_device_detects_ps5(self):
        """find_controller_device() detects a PS5 DualSense by name"""
        from robot_controllers.ps4_controller import find_controller_device

        proc_content = (
            "I: Bus=0005 Vendor=054c Product=0ce6 Version=0100\n"
            "N: Name=\"DualSense Wireless Controller\"\n"
            "P: Phys=aa:bb:cc:dd:ee:ff\n"
            "S: Sysfs=/devices/virtual/misc/uhid/0005:054C:0CE6.0001/input/input3\n"
            "U: Uniq=aa:bb:cc:dd:ee:ff\n"
            "H: Handlers=event4 js0\n"
            "B: EV=1b\n"
        )
        with patch("builtins.open", mock_open(read_data=proc_content)):
            result = find_controller_device()
        assert result == "/dev/input/event4"

    def test_find_controller_device_detects_ps5_bluetooth_name(self):
        """find_controller_device() detects the full Bluetooth PS5 device name"""
        from robot_controllers.ps4_controller import find_controller_device

        proc_content = (
            "I: Bus=0005 Vendor=054c Product=0ce6 Version=0100\n"
            "N: Name=\"Sony Interactive Entertainment DualSense Wireless Controller\"\n"
            "P: Phys=aa:bb:cc:dd:ee:ff\n"
            "H: Handlers=event3 js0\n"
            "B: EV=1b\n"
        )
        with patch("builtins.open", mock_open(read_data=proc_content)):
            result = find_controller_device()
        assert result == "/dev/input/event3"

    def test_find_controller_device_detects_ps4(self):
        """find_controller_device() detects a PS4 DualShock 4 by name"""
        from robot_controllers.ps4_controller import find_controller_device

        proc_content = (
            "I: Bus=0005 Vendor=054c Product=05c4 Version=0100\n"
            "N: Name=\"Sony Interactive Entertainment Wireless Controller\"\n"
            "P: Phys=aa:bb:cc:dd:ee:ff\n"
            "H: Handlers=event5 js0\n"
            "B: EV=1b\n"
        )
        with patch("builtins.open", mock_open(read_data=proc_content)):
            result = find_controller_device()
        assert result == "/dev/input/event5"

    def test_find_controller_device_returns_none_for_unknown_device(self):
        """find_controller_device() returns None when no PlayStation controller is present"""
        from robot_controllers.ps4_controller import find_controller_device

        proc_content = (
            "I: Bus=0011 Vendor=0001 Product=0001 Version=ab41\n"
            "N: Name=\"AT Translated Set 2 keyboard\"\n"
            "H: Handlers=sysrq kbd event0 leds\n"
            "B: EV=120013\n"
        )
        with patch("builtins.open", mock_open(read_data=proc_content)):
            result = find_controller_device()
        assert result is None

    def test_find_controller_device_selects_first_matching_device(self):
        """find_controller_device() returns the first matching device when multiple are listed"""
        from robot_controllers.ps4_controller import find_controller_device

        proc_content = (
            "I: Bus=0011 Vendor=0001 Product=0001 Version=ab41\n"
            "N: Name=\"AT Translated Set 2 keyboard\"\n"
            "H: Handlers=sysrq kbd event0 leds\n"
            "B: EV=120013\n"
            "\n"
            "I: Bus=0005 Vendor=054c Product=0ce6 Version=0100\n"
            "N: Name=\"DualSense Wireless Controller\"\n"
            "H: Handlers=event4 js0\n"
            "B: EV=1b\n"
            "\n"
            "I: Bus=0005 Vendor=054c Product=05c4 Version=0100\n"
            "N: Name=\"Sony Interactive Entertainment Wireless Controller\"\n"
            "H: Handlers=event6 js1\n"
            "B: EV=1b\n"
        )
        with patch("builtins.open", mock_open(read_data=proc_content)):
            result = find_controller_device()
        # The PS5 DualSense entry comes first in the file, so event4 is returned
        assert result == "/dev/input/event4"

    def test_find_controller_device_skips_ps5_touchpad_sub_device(self):
        """find_controller_device() must not return the touchpad event node.

        When a PS5 DualSense is connected via Bluetooth the Linux HID driver
        exposes several separate input devices.  The touchpad sub-device has a
        name like "DualSense Wireless Controller Touchpad" and its event node
        must be skipped so that the main gamepad node is returned instead.
        """
        from robot_controllers.ps4_controller import find_controller_device

        # Touchpad entry appears BEFORE the main gamepad entry – this was the
        # failure mode reported in the Codex review.
        proc_content = (
            "I: Bus=0005 Vendor=054c Product=0ce6 Version=0100\n"
            "N: Name=\"DualSense Wireless Controller Touchpad\"\n"
            "H: Handlers=event3\n"
            "B: EV=1b\n"
            "\n"
            "I: Bus=0005 Vendor=054c Product=0ce6 Version=0100\n"
            "N: Name=\"DualSense Wireless Controller\"\n"
            "H: Handlers=event4 js0\n"
            "B: EV=1b\n"
        )
        with patch("builtins.open", mock_open(read_data=proc_content)):
            result = find_controller_device()
        # event3 (touchpad) must be skipped; event4 (gamepad) must be returned
        assert result == "/dev/input/event4"

    def test_find_controller_device_skips_ps4_touchpad_sub_device(self):
        """find_controller_device() skips the PS4 touchpad event node."""
        from robot_controllers.ps4_controller import find_controller_device

        proc_content = (
            "I: Bus=0005 Vendor=054c Product=05c4 Version=0100\n"
            "N: Name=\"Sony Interactive Entertainment Wireless Controller Touchpad\"\n"
            "H: Handlers=event2\n"
            "B: EV=1b\n"
            "\n"
            "I: Bus=0005 Vendor=054c Product=05c4 Version=0100\n"
            "N: Name=\"Sony Interactive Entertainment Wireless Controller\"\n"
            "H: Handlers=event5 js0\n"
            "B: EV=1b\n"
        )
        with patch("builtins.open", mock_open(read_data=proc_content)):
            result = find_controller_device()
        assert result == "/dev/input/event5"

    def test_find_controller_device_skips_motion_sensors_sub_device(self):
        """find_controller_device() skips motion-sensor sub-devices."""
        from robot_controllers.ps4_controller import find_controller_device

        proc_content = (
            "I: Bus=0005 Vendor=054c Product=0ce6 Version=0100\n"
            "N: Name=\"DualSense Wireless Controller Motion Sensors\"\n"
            "H: Handlers=event6\n"
            "B: EV=1b\n"
            "\n"
            "I: Bus=0005 Vendor=054c Product=0ce6 Version=0100\n"
            "N: Name=\"DualSense Wireless Controller\"\n"
            "H: Handlers=event7 js0\n"
            "B: EV=1b\n"
        )
        with patch("builtins.open", mock_open(read_data=proc_content)):
            result = find_controller_device()
        assert result == "/dev/input/event7"

    def test_find_controller_device_skips_all_non_gamepad_sub_devices(self):
        """find_controller_device() skips touchpad AND motion-sensors, returns gamepad."""
        from robot_controllers.ps4_controller import find_controller_device

        # All three kernel sub-devices appear before the main gamepad
        proc_content = (
            "I: Bus=0005 Vendor=054c Product=0ce6 Version=0100\n"
            "N: Name=\"DualSense Wireless Controller Touchpad\"\n"
            "H: Handlers=event3\n"
            "B: EV=1b\n"
            "\n"
            "I: Bus=0005 Vendor=054c Product=0ce6 Version=0100\n"
            "N: Name=\"DualSense Wireless Controller Motion Sensors\"\n"
            "H: Handlers=event4\n"
            "B: EV=1b\n"
            "\n"
            "I: Bus=0005 Vendor=054c Product=0ce6 Version=0100\n"
            "N: Name=\"DualSense Wireless Controller\"\n"
            "H: Handlers=event5 js0\n"
            "B: EV=1b\n"
        )
        with patch("builtins.open", mock_open(read_data=proc_content)):
            result = find_controller_device()
        assert result == "/dev/input/event5"

    def test_excluded_device_keywords_constant_exists(self):
        """EXCLUDED_DEVICE_KEYWORDS constant is defined and contains expected keywords."""
        from robot_controllers.ps4_controller import EXCLUDED_DEVICE_KEYWORDS

        assert isinstance(EXCLUDED_DEVICE_KEYWORDS, list)
        assert len(EXCLUDED_DEVICE_KEYWORDS) > 0
        keywords_lower = [kw.lower() for kw in EXCLUDED_DEVICE_KEYWORDS]
        assert "touchpad" in keywords_lower
        assert any("motion" in kw for kw in keywords_lower)

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

    def test_run_dispatches_cross_button_press(self):
        """A real BTN_SOUTH evdev event reaches the Cross callback."""
        event = struct.pack("llHHI", 0, 0, 1, 304, 1)
        mock_event_file = MagicMock()
        mock_event_file.read.side_effect = [event, b""]

        received = []
        self.controller.onCrossButton(lambda sender: received.append(sender))
        with patch("robot_controllers.ps4_controller.find_controller_device",
                   return_value="/dev/input/event99"), \
             patch("builtins.open", return_value=mock_event_file):
            self.controller.run()

        assert received == [self.controller]

    def test_run_preserves_small_right_stick_movement_for_turret(self):
        """The controller must not apply a second turret deadzone."""
        # 147 is a small-but-deliberate 8-bit horizontal movement (~15/100).
        event = struct.pack("llHHI", 0, 0, 3, 3, 147)
        mock_event_file = MagicMock()
        mock_event_file.read.side_effect = [event, b""]

        received_x_values = []
        self.controller.onRightJoystickMove(
            lambda sender: received_x_values.append(sender.r_left)
        )
        with patch("robot_controllers.ps4_controller.find_controller_device",
                   return_value="/dev/input/event99"), \
             patch("builtins.open", return_value=mock_event_file):
            self.controller.run()

        assert len(received_x_values) == 1
        assert abs(received_x_values[0]) > 10
        assert abs(received_x_values[0]) < 20

    def test_debug_input_can_be_enabled(self):
        """Controller input diagnostics are opt-in."""
        self.controller.set_debug_input(True)
        assert self.controller._debug_input is True
    
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

    # --- Button mapping correctness tests ---

    def test_cross_button_triggers_cross_button_event(self):
        """Cross (X) button fires 'cross_button' event"""
        received = []
        self.controller.onCrossButton(lambda s: received.append("cross_button"))
        self.controller.trigger("cross_button")
        assert received == ["cross_button"]

    def test_circle_button_triggers_circle_button_event(self):
        """Circle button fires 'circle_button' event (not triangle_button)"""
        received = []
        self.controller.onCircleButton(lambda s: received.append("circle_button"))
        self.controller.trigger("circle_button")
        assert received == ["circle_button"]

    def test_triangle_button_triggers_triangle_button_event(self):
        """Triangle button fires 'triangle_button' event"""
        received = []
        self.controller.onTriangleButton(lambda s: received.append("triangle_button"))
        self.controller.trigger("triangle_button")
        assert received == ["triangle_button"]

    def test_square_button_triggers_square_button_event(self):
        """Square button fires 'square_button' event (not triangle_button)"""
        received = []
        self.controller.onSquareButton(lambda s: received.append("square_button"))
        self.controller.trigger("square_button")
        assert received == ["square_button"]

    def test_circle_does_not_trigger_triangle_event(self):
        """Triggering circle_button does NOT fire triangle_button callbacks"""
        triangle_received = []
        self.controller.onTriangleButton(lambda s: triangle_received.append("triangle"))
        # Simulate what the fixed code does for circle button press
        self.controller.trigger("circle_button")
        assert triangle_received == [], "circle_button must not fire triangle_button callbacks"

    def test_square_does_not_trigger_triangle_event(self):
        """Triggering square_button does NOT fire triangle_button callbacks"""
        triangle_received = []
        self.controller.onTriangleButton(lambda s: triangle_received.append("triangle"))
        # Simulate what the fixed code does for square button press
        self.controller.trigger("square_button")
        assert triangle_received == [], "square_button must not fire triangle_button callbacks"

    def test_each_button_fires_only_its_own_callback(self):
        """Each face button triggers exactly its own registered callback and no others"""
        results = {"cross": 0, "circle": 0, "triangle": 0, "square": 0}
        self.controller.onCrossButton(lambda s: results.__setitem__("cross", results["cross"] + 1))
        self.controller.onCircleButton(lambda s: results.__setitem__("circle", results["circle"] + 1))
        self.controller.onTriangleButton(lambda s: results.__setitem__("triangle", results["triangle"] + 1))
        self.controller.onSquareButton(lambda s: results.__setitem__("square", results["square"] + 1))

        self.controller.trigger("cross_button")
        assert results == {"cross": 1, "circle": 0, "triangle": 0, "square": 0}

        self.controller.trigger("circle_button")
        assert results == {"cross": 1, "circle": 1, "triangle": 0, "square": 0}

        self.controller.trigger("triangle_button")
        assert results == {"cross": 1, "circle": 1, "triangle": 1, "square": 0}

        self.controller.trigger("square_button")
        assert results == {"cross": 1, "circle": 1, "triangle": 1, "square": 1}

    @pytest.mark.parametrize("event_name,callback_method", [
        ("cross_button", "onCrossButton"),
        ("circle_button", "onCircleButton"),
        ("triangle_button", "onTriangleButton"),
        ("square_button", "onSquareButton"),
        ("left_joystick", "onLeftJoystickMove"),
        ("right_joystick", "onRightJoystickMove"),
        ("options_button", "onOptionsButton"),
        ("l1_button", "onL1Button"),
        ("r1_button", "onR1Button"),
        ("l2_button", "onL2Button"),
        ("r2_button", "onR2Button"),
        ("left_arrow_pressed", "onLeftArrowPressed"),
        ("right_arrow_pressed", "onRightArrowPressed"),
        ("up_arrow_pressed", "onUpArrowPressed"),
        ("down_arrow_pressed", "onDownArrowPressed"),
        ("lr_arrow_released", "onLRArrowReleased"),
        ("ud_arrow_released", "onUDArrowReleased"),
    ])
    def test_callback_method_exists(self, event_name, callback_method):
        """Test that every callback registration method exists and is callable"""
        assert hasattr(self.controller, callback_method)
        
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
        from robot_controllers.ps4_controller import report_controller_error, report_exception
        
        assert callable(report_controller_error)
        assert callable(report_exception)
    
    def test_struct_operations(self):
        """Test struct operations for binary data parsing"""
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


class TestPS4ControllerAxisScaling:
    """Tests for PS4/PS5 joystick axis normalization."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.controller = PS4Controller()

    def test_8bit_axis_scaling(self):
        assert self.controller._scale_axis(0, (1000, -1000)) == 1000
        assert self.controller._scale_axis(254, (1000, -1000)) == pytest.approx(-992.16, abs=1)
        assert abs(self.controller._scale_axis(127, (1000, -1000))) < 50
        assert self.controller._scale_axis(255, (1000, -1000)) is None

    def test_16bit_axis_scaling(self):
        center = self.controller._scale_axis(32768, (-1000, 1000))
        assert center is not None
        assert abs(center) < 50

        forward = self.controller._scale_axis(0, (1000, -1000))
        assert forward == 1000

        backward = self.controller._scale_axis(65535, (1000, -1000))
        assert backward == -1000

    def test_sentinel_values_are_ignored(self):
        assert self.controller._scale_axis(255, (-1000, 1000)) is None
        assert self.controller._scale_axis(4294967295, (-1000, 1000)) is None

class TestPS4ControllerTelemetry:
    """Telemetry tests for PS4Controller (PEN-165)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.controller = PS4Controller()
        from telemetry.collector import TelemetryCollector
        self.collector = TelemetryCollector()
        self.controller.set_telemetry_collector(self.collector)

    def test_controller_type_attribute_is_ps4(self):
        assert self.controller._controller_type == "ps4"

    @pytest.mark.parametrize("event_name", [
        "cross_button",
        "left_joystick",
        "right_joystick",
        "l1_button",
        "r1_button",
    ])
    def test_trigger_produces_command_received_with_ps4_controller_type(self, event_name):
        self.controller.trigger(event_name)
        received = next(
            e for e in self.collector.peek() if e["event_type"] == "command_received"
        )
        assert received["payload"]["controller_type"] == "ps4"

    @pytest.mark.parametrize("event_name", [
        "cross_button",
        "left_joystick",
        "square_button",
    ])
    def test_trigger_produces_command_executed_with_ps4_controller_type(self, event_name):
        self.controller.trigger(event_name)
        executed = next(
            e for e in self.collector.peek() if e["event_type"] == "command_executed"
        )
        assert executed["payload"]["controller_type"] == "ps4"

    def test_command_received_and_command_executed_both_emitted(self):
        self.controller.trigger("cross_button")
        types = {e["event_type"] for e in self.collector.peek()}
        assert "command_received" in types
        assert "command_executed" in types

    def test_command_executed_success_true_with_no_raising_callback(self):
        self.controller.on("cross_button", lambda s: None)
        self.controller.trigger("cross_button")
        executed = next(
            e for e in self.collector.peek() if e["event_type"] == "command_executed"
        )
        assert executed["payload"]["success"] is True

    def test_events_pass_schema_validation(self):
        from telemetry.schemas import validate_event
        self.controller.trigger("cross_button")
        for event in self.collector.peek():
            validate_event(event)


class TestWaitForConnection:
    """Tests for wait_for_connection() (PEN-166 follow-up)."""

    def test_returns_immediately_when_already_connected(self):
        controller = Mock()
        controller.is_connected.return_value = True
        sleep_fn = Mock()

        connected, elapsed = wait_for_connection(controller, sleep_fn=sleep_fn)

        assert connected is True
        assert elapsed == 0.0
        sleep_fn.assert_not_called()

    def test_polls_until_connected_within_timeout(self):
        controller = Mock()
        # Not connected for the first two checks, connected on the third.
        controller.is_connected.side_effect = [False, False, True]
        sleep_fn = Mock()

        connected, elapsed = wait_for_connection(
            controller, timeout=1.0, poll_interval=0.1, sleep_fn=sleep_fn
        )

        assert connected is True
        assert elapsed == pytest.approx(0.2)
        assert sleep_fn.call_count == 2
        sleep_fn.assert_called_with(0.1)

    def test_gives_up_after_timeout_elapses(self):
        controller = Mock()
        controller.is_connected.return_value = False
        sleep_fn = Mock()

        connected, elapsed = wait_for_connection(
            controller, timeout=0.3, poll_interval=0.1, sleep_fn=sleep_fn
        )

        assert connected is False
        assert elapsed == pytest.approx(0.3)
        # elapsed reaches (but does not exceed) timeout after 3 polls; the
        # loop then exits on the elapsed >= timeout check without sleeping again.
        assert sleep_fn.call_count == 3

    def test_default_sleep_fn_uses_time_sleep(self):
        controller = Mock()
        controller.is_connected.return_value = True

        with patch("robot_controllers.ps4_controller._sleep") as mock_sleep:
            connected, elapsed = wait_for_connection(controller)

        assert connected is True
        mock_sleep.assert_not_called()


# Tests can be run with: pytest tests/test_ps4_controller.py