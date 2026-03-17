#!/usr/bin/env python3

"""
Unit tests for error_reporter module using pytest
"""

import pytest
import io
import sys
from unittest.mock import patch
from error_reporting import report_exception, report_device_error, report_controller_error

class TestErrorReporter:
    
    def capture_print_output(self, func, *args, **kwargs):
        """Helper to capture print output from error reporting functions"""
        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            func(*args, **kwargs)
        return captured_output.getvalue()
    
    def test_report_exception_basic(self):
        """Test basic exception reporting"""
        test_exception = ValueError("Test error message")
        
        output = self.capture_print_output(
            report_exception,
            "test_function",
            "testing basic functionality", 
            test_exception
        )
        
        assert "EXCEPTION in test_function - testing basic functionality:" in output
        assert "Error type: ValueError" in output
        assert "Error details: Test error message" in output
        assert "Location: testing basic functionality" in output
    
    def test_report_exception_with_context(self):
        """Test exception reporting with additional context"""
        test_exception = RuntimeError("Runtime error occurred")
        additional_context = "User ID: 123, Action: save_data"
        
        output = self.capture_print_output(
            report_exception,
            "save_user_data",
            "saving user preferences",
            test_exception,
            additional_context
        )
        
        assert "EXCEPTION in save_user_data - saving user preferences:" in output
        assert "Error type: RuntimeError" in output
        assert "Error details: Runtime error occurred" in output
        assert "Location: saving user preferences" in output
        assert "Context: User ID: 123, Action: save_data" in output
    
    def test_report_exception_without_context(self):
        """Test exception reporting without additional context"""
        test_exception = KeyError("missing_key")
        
        output = self.capture_print_output(
            report_exception,
            "get_config",
            "retrieving configuration",
            test_exception
        )
        
        assert "EXCEPTION in get_config - retrieving configuration:" in output
        assert "Error type: KeyError" in output
        assert "Error details: 'missing_key'" in output  # KeyError adds quotes
        assert "Location: retrieving configuration" in output
        # Should not contain "Context:" line when no additional context
        assert "Context:" not in output or "Context: None" not in output
    
    def test_report_device_error_basic(self):
        """Test basic device error reporting"""
        test_exception = ConnectionError("Device not responding")
        
        output = self.capture_print_output(
            report_device_error,
            "motor_left",
            "initialize_motor",
            test_exception
        )
        
        assert "DEVICE EXCEPTION - initialize_motor:" in output
        assert "Error type: ConnectionError" in output
        assert "Error details: Device not responding" in output
        assert "Context: Device: motor_left | Operation: initialize_motor" in output
    
    def test_report_device_error_with_port(self):
        """Test device error reporting with port information"""
        test_exception = OSError("Port access denied")
        
        output = self.capture_print_output(
            report_device_error,
            "ultrasonic_sensor",
            "read_distance",
            test_exception,
            "Port.S2"
        )
        
        assert "DEVICE EXCEPTION - read_distance:" in output
        assert "Error type: OSError" in output
        assert "Error details: Port access denied" in output
        assert "Context: Device: ultrasonic_sensor | Operation: read_distance | Port: Port.S2" in output
    
    def test_report_device_error_without_port(self):
        """Test device error reporting without port information"""
        test_exception = ValueError("Invalid configuration")
        
        output = self.capture_print_output(
            report_device_error,
            "gyro_sensor",
            "calibrate",
            test_exception
        )
        
        assert "DEVICE EXCEPTION - calibrate:" in output
        assert "Error type: ValueError" in output
        assert "Error details: Invalid configuration" in output
        assert "Context: Device: gyro_sensor | Operation: calibrate" in output
        assert "Port:" not in output
    
    def test_report_controller_error_basic(self):
        """Test basic controller error reporting"""
        test_exception = FileNotFoundError("Controller device not found")
        
        output = self.capture_print_output(
            report_controller_error,
            "PS4Controller",
            "connect_device",
            test_exception
        )
        
        assert "CONTROLLER EXCEPTION - connect_device:" in output
        assert "Error type: FileNotFoundError" in output
        assert "Error details: Controller device not found" in output
        assert "Context: Controller: PS4Controller | Operation: connect_device" in output
    
    def test_report_controller_error_with_path(self):
        """Test controller error reporting with device path"""
        test_exception = PermissionError("Access denied to device")
        
        output = self.capture_print_output(
            report_controller_error,
            "RemoteController",
            "open_socket",
            test_exception,
            "/dev/input/js0"
        )
        
        assert "CONTROLLER EXCEPTION - open_socket:" in output
        assert "Error type: PermissionError" in output
        assert "Error details: Access denied to device" in output
        assert "Context: Controller: RemoteController | Operation: open_socket | Path: /dev/input/js0" in output
    
    def test_report_controller_error_without_path(self):
        """Test controller error reporting without device path"""
        test_exception = TimeoutError("Connection timeout")
        
        output = self.capture_print_output(
            report_controller_error,
            "NetworkController",
            "establish_connection",
            test_exception
        )
        
        assert "CONTROLLER EXCEPTION - establish_connection:" in output
        assert "Error type: TimeoutError" in output
        assert "Error details: Connection timeout" in output
        assert "Context: Controller: NetworkController | Operation: establish_connection" in output
        assert "Path:" not in output
    
    @pytest.mark.parametrize("exception_type,exception_message,expected_detail", [
        (ValueError, "Invalid value provided", "Invalid value provided"),
        (TypeError, "Wrong type passed", "Wrong type passed"),
        (AttributeError, "Attribute not found", "Attribute not found"),
        (IndexError, "List index out of range", "List index out of range"),
        (KeyError, "Dictionary key missing", "'Dictionary key missing'"),  # KeyError adds quotes
        (OSError, "Input/output operation failed", "Input/output operation failed"),
        (RuntimeError, "Runtime error occurred", "Runtime error occurred"),
    ])
    def test_different_exception_types(self, exception_type, exception_message, expected_detail):
        """Test error reporting with various exception types"""
        test_exception = exception_type(exception_message)
        
        output = self.capture_print_output(
            report_exception,
            "test_function",
            "testing exception handling",
            test_exception
        )
        
        assert f"Error type: {exception_type.__name__}" in output
        assert f"Error details: {expected_detail}" in output
    
    def test_empty_exception_message(self):
        """Test error reporting with empty exception message"""
        test_exception = ValueError("")
        
        output = self.capture_print_output(
            report_exception,
            "test_function",
            "testing empty message",
            test_exception
        )
        
        assert "Error type: ValueError" in output
        assert "Error details:" in output  # Should still have the label
    
    def test_special_characters_in_messages(self):
        """Test error reporting with special characters"""
        test_exception = RuntimeError("Error with special chars: !@#$%^&*()[]{}|\\:;\"'<>?,./")
        
        output = self.capture_print_output(
            report_exception,
            "special_chars_test",
            "testing special characters",
            test_exception
        )
        
        assert "Error type: RuntimeError" in output
        assert "Error with special chars:" in output
    
    def test_unicode_characters_in_messages(self):
        """Test error reporting with unicode characters"""
        test_exception = UnicodeError("Unicode error: café résumé naïve")
        
        output = self.capture_print_output(
            report_exception,
            "unicode_test",
            "testing unicode handling",
            test_exception
        )
        
        assert "Error type: UnicodeError" in output
        assert "café résumé naïve" in output
    
    def test_very_long_error_message(self):
        """Test error reporting with very long error message"""
        long_message = "A" * 1000  # 1000 character error message
        test_exception = ValueError(long_message)
        
        output = self.capture_print_output(
            report_exception,
            "long_message_test",
            "testing long error messages",
            test_exception
        )
        
        assert "Error type: ValueError" in output
        assert long_message in output
    
    def test_none_values_handling(self):
        """Test error reporting with None values where applicable"""
        test_exception = RuntimeError("Test error")
        
        # Test with None additional_context
        output = self.capture_print_output(
            report_exception,
            "test_function",
            "testing none values",
            test_exception,
            None
        )
        
        assert "Error type: RuntimeError" in output
        # Should not print "Context: None"
        lines = output.split('\n')
        context_lines = [line for line in lines if line.strip().startswith("Context:")]
        assert len(context_lines) == 0  # No context line should be printed for None
    
    def test_nested_exception_str_representation(self):
        """Test error reporting with exceptions that have complex str representations"""
        # Create a custom exception with complex string representation
        class ComplexException(Exception):
            def __str__(self):
                return "Complex error with multiple lines\nLine 2\nLine 3"
        
        test_exception = ComplexException()
        
        output = self.capture_print_output(
            report_exception,
            "complex_test",
            "testing complex exception",
            test_exception
        )
        
        assert "Error type: ComplexException" in output
        assert "Complex error with multiple lines" in output
        assert "Line 2" in output
        assert "Line 3" in output

# Tests can be run with: pytest tests/test_error_reporter.py