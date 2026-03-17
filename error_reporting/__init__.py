"""
Error Reporting Library

Provides consistent error reporting utilities for robotics applications,
especially designed for EV3 MicroPython where traceback is not available.
"""

from .error_reporter import (
    report_exception,
    report_device_error,
    report_controller_error
)

__version__ = "1.0.0"
__all__ = [
    "report_exception",
    "report_device_error", 
    "report_controller_error"
]