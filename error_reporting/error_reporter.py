#!/usr/bin/env pybricks-micropython

"""
Error reporting utilities for EV3 MicroPython

Since traceback module is not available on EV3, this module provides
consistent error reporting with context information.
"""

def report_exception(function_name, location_description, exception, additional_context=None):
    """
    Report an exception with consistent formatting and context information.
    
    Args:
        function_name: Name of the function where exception occurred
        location_description: Description of what was being attempted
        exception: The caught exception object
        additional_context: Optional additional context information
    """
    print("EXCEPTION in {} - {}:".format(function_name, location_description))
    print("Error type:", type(exception).__name__)
    print("Error details:", str(exception))
    print("Location:", location_description)
    if additional_context:
        print("Context:", additional_context)

def report_device_error(device_name, operation, exception, port=None):
    """
    Report a device-related exception with device-specific context.
    
    Args:
        device_name: Name of the device that failed
        operation: What operation was being performed
        exception: The caught exception object
        port: Optional port information
    """
    context = "Device: {} | Operation: {}".format(device_name, operation)
    if port:
        context += " | Port: {}".format(port)
    
    print("DEVICE EXCEPTION - {}:".format(operation))
    print("Error type:", type(exception).__name__)
    print("Error details:", str(exception))
    print("Context:", context)

def report_controller_error(controller_type, operation, exception, path=None):
    """
    Report a controller-related exception with controller-specific context.
    
    Args:
        controller_type: Type of controller (e.g., "PS4Controller")
        operation: What operation was being performed
        exception: The caught exception object
        path: Optional device path information
    """
    context = "Controller: {} | Operation: {}".format(controller_type, operation)
    if path:
        context += " | Path: {}".format(path)
    
    print("CONTROLLER EXCEPTION - {}:".format(operation))
    print("Error type:", type(exception).__name__)
    print("Error details:", str(exception))
    print("Context:", context)