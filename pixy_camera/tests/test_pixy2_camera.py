#!/usr/bin/env python3

"""
Unit tests for Pixy2Camera class using pytest
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import threading
from time import sleep

from pixy_camera import Pixy2Camera

class TestPixy2Camera:
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures"""
        # Mock the Pixy2 hardware since we don't have actual hardware in tests
        with patch('pixy_camera.pixy2_camera.Pixy2') as mock_pixy2:
            mock_pixy2_instance = Mock()
            mock_pixy2.return_value = mock_pixy2_instance
            
            self.mock_pixy2_class = mock_pixy2
            self.mock_pixy2_instance = mock_pixy2_instance
            self.camera = Pixy2Camera(port=1)
            
            # Track callback calls
            self.callback_calls = []
            self.callback_args = []
    
    def test_initialization(self):
        """Test camera initialization"""
        # Verify Pixy2 was instantiated with correct parameters
        self.mock_pixy2_class.assert_called_once_with(port=1, i2c_address=0x54)
        
        # Verify mode was set
        assert self.camera.pixy.mode == 'SIG1'
        
        # Verify initial state
        assert self.camera.stopped == False
        assert self.camera.blocks is None
    
    def test_str_representation(self):
        """Test string representation"""
        assert str(self.camera) == "Pixy Camera Controller for EV3"
    
    def test_close(self):
        """Test camera close method"""
        self.camera.close()
        self.mock_pixy2_instance.close.assert_called_once()
    
    def test_light_on(self):
        """Test turning light on"""
        self.camera.light(True)
        self.mock_pixy2_instance.set_lamp.assert_called_once_with(True, True)
    
    def test_light_off(self):
        """Test turning light off"""
        self.camera.light(False)
        self.mock_pixy2_instance.set_lamp.assert_called_once_with(False, False)
    
    def test_on_block_detected_callback_registration(self):
        """Test block detected callback registration"""
        def test_callback(sender):
            self.callback_calls.append("block_detected")
            self.callback_args.append(sender)
        
        self.camera.onBlockDetected(test_callback)
        
        # Verify callback was registered (checking internal structure)
        assert self.camera.callbacks is not None
        assert "block_detected" in self.camera.callbacks
        assert test_callback in self.camera.callbacks["block_detected"]
    
    def test_multiple_block_detected_callbacks(self):
        """Test multiple block detected callbacks"""
        def callback1(sender):
            self.callback_calls.append("callback1")
        
        def callback2(sender):
            self.callback_calls.append("callback2")
        
        self.camera.onBlockDetected(callback1)
        self.camera.onBlockDetected(callback2)
        
        # Verify both callbacks were registered
        assert len(self.camera.callbacks["block_detected"]) == 2
        assert callback1 in self.camera.callbacks["block_detected"]
        assert callback2 in self.camera.callbacks["block_detected"]
    
    def test_run_no_blocks_detected(self):
        """Test run loop when no blocks are detected"""
        # Mock get_blocks to return no blocks
        self.mock_pixy2_instance.get_blocks.return_value = (0, [])
        
        def test_callback(sender):
            self.callback_calls.append("block_detected")
        
        self.camera.onBlockDetected(test_callback)
        
        # Start camera in thread and let it run briefly
        camera_thread = threading.Thread(target=self.camera.run)
        camera_thread.daemon = True
        camera_thread.start()
        
        # Let it run for a short time
        sleep(0.05)
        
        # Stop the camera
        self.camera.stopped = True
        camera_thread.join(timeout=0.1)
        
        # Verify get_blocks was called but no callbacks triggered
        assert self.mock_pixy2_instance.get_blocks.call_count >= 1
        assert len(self.callback_calls) == 0
    
    def test_run_blocks_detected(self):
        """Test run loop when blocks are detected"""
        # Mock get_blocks to return blocks
        mock_blocks = [{"x": 100, "y": 50, "width": 30, "height": 20}]
        self.mock_pixy2_instance.get_blocks.return_value = (1, mock_blocks)
        
        def test_callback(sender):
            self.callback_calls.append("block_detected")
            self.callback_args.append(sender)
        
        self.camera.onBlockDetected(test_callback)
        
        # Start camera in thread and let it run briefly
        camera_thread = threading.Thread(target=self.camera.run)
        camera_thread.daemon = True
        camera_thread.start()
        
        # Let it run for a short time to detect blocks
        sleep(0.15)  # Allow multiple detection cycles
        
        # Stop the camera
        self.camera.stopped = True
        camera_thread.join(timeout=0.1)
        
        # Verify blocks were detected and callback was triggered
        assert self.mock_pixy2_instance.get_blocks.call_count >= 1
        assert len(self.callback_calls) >= 1
        assert all(call == "block_detected" for call in self.callback_calls)
        assert all(arg == self.camera for arg in self.callback_args)
        assert self.camera.blocks == mock_blocks
    
    def test_run_multiple_callbacks_triggered(self):
        """Test that multiple callbacks are triggered when blocks detected"""
        # Mock get_blocks to return blocks
        mock_blocks = [{"x": 100, "y": 50}]
        self.mock_pixy2_instance.get_blocks.return_value = (1, mock_blocks)
        
        callback1_calls = []
        callback2_calls = []
        
        def callback1(sender):
            callback1_calls.append("triggered")
        
        def callback2(sender):
            callback2_calls.append("triggered")
        
        self.camera.onBlockDetected(callback1)
        self.camera.onBlockDetected(callback2)
        
        # Start camera in thread
        camera_thread = threading.Thread(target=self.camera.run)
        camera_thread.daemon = True
        camera_thread.start()
        
        # Let it run briefly
        sleep(0.15)
        
        # Stop the camera
        self.camera.stopped = True
        camera_thread.join(timeout=0.1)
        
        # Verify both callbacks were triggered
        assert len(callback1_calls) >= 1
        assert len(callback2_calls) >= 1
    
    def test_run_stops_when_stopped_flag_set(self):
        """Test that run loop stops when stopped flag is set"""
        # Mock get_blocks to return no blocks
        self.mock_pixy2_instance.get_blocks.return_value = (0, [])
        
        # Start camera
        camera_thread = threading.Thread(target=self.camera.run)
        camera_thread.daemon = True
        camera_thread.start()
        
        # Let it run briefly
        sleep(0.05)
        
        # Set stopped flag
        self.camera.stopped = True
        
        # Thread should stop within reasonable time
        camera_thread.join(timeout=0.5)
        assert not camera_thread.is_alive()
    
    def test_blocks_boundary_condition(self):
        """Test behavior when exactly 1 block is detected (boundary condition)"""
        # Mock get_blocks to return exactly 1 block
        mock_blocks = [{"x": 150, "y": 100}]
        self.mock_pixy2_instance.get_blocks.return_value = (1, mock_blocks)
        
        def test_callback(sender):
            self.callback_calls.append("detected")
        
        self.camera.onBlockDetected(test_callback)
        
        # Start camera
        camera_thread = threading.Thread(target=self.camera.run)
        camera_thread.daemon = True
        camera_thread.start()
        
        sleep(0.15)
        
        self.camera.stopped = True
        camera_thread.join(timeout=0.1)
        
        # Should trigger callback since nr_blocks >= 1
        assert len(self.callback_calls) >= 1
    
    def test_get_blocks_parameters(self):
        """Test that get_blocks is called with correct parameters"""
        self.mock_pixy2_instance.get_blocks.return_value = (0, [])
        
        # Start camera briefly
        camera_thread = threading.Thread(target=self.camera.run)
        camera_thread.daemon = True
        camera_thread.start()
        
        sleep(0.05)
        
        self.camera.stopped = True
        camera_thread.join(timeout=0.1)
        
        # Verify get_blocks was called with correct parameters (1, 1)
        self.mock_pixy2_instance.get_blocks.assert_called_with(1, 1)
    
    @pytest.mark.parametrize("port_number", [1, 2, 3, 4])
    def test_initialization_different_ports(self, port_number):
        """Test initialization with different port numbers"""
        with patch('pixy_camera.pixy2_camera.Pixy2') as mock_pixy2:
            mock_pixy2_instance = Mock()
            mock_pixy2.return_value = mock_pixy2_instance
            
            camera = Pixy2Camera(port=port_number)
            
            # Note: The current implementation always uses port=1 in Pixy2 constructor
            # This might be a bug in the original code, but we test the current behavior
            mock_pixy2.assert_called_once_with(port=1, i2c_address=0x54)
    
    def test_inheritance_from_event_handler(self):
        """Test that Pixy2Camera properly inherits from EventHandler"""
        from event_handler import EventHandler
        assert isinstance(self.camera, EventHandler)
        
        # Test that EventHandler methods are available
        assert hasattr(self.camera, 'on')
        assert hasattr(self.camera, 'trigger')
        assert hasattr(self.camera, 'callbacks')
    
    def test_inheritance_from_threading_thread(self):
        """Test that Pixy2Camera properly inherits from threading.Thread"""
        assert isinstance(self.camera, threading.Thread)
        
        # Test that Thread methods are available
        assert hasattr(self.camera, 'start')
        assert hasattr(self.camera, 'join')
        assert hasattr(self.camera, 'is_alive')
    
    def test_trigger_block_detected_manually(self):
        """Test manually triggering block_detected event"""
        def test_callback(sender):
            self.callback_calls.append("manual_trigger")
            self.callback_args.append(sender)
        
        self.camera.onBlockDetected(test_callback)
        self.camera.trigger("block_detected")
        
        assert len(self.callback_calls) == 1
        assert self.callback_calls[0] == "manual_trigger"
        assert self.callback_args[0] == self.camera

# Tests can be run with: pytest tests/test_pixy2_camera.py