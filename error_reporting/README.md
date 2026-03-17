# Error Reporting Library

A lightweight error reporting library designed for robotics applications, especially EV3 MicroPython environments where the standard `traceback` module is not available.

## Features

- Consistent error reporting across different error types
- Device-specific error reporting for hardware failures
- Controller-specific error reporting for input device issues
- No external dependencies - works with MicroPython
- Structured error output with context information
- Lightweight and fast

## Installation

```bash
pip install -e .
```

## Usage

### Basic Exception Reporting

```python
from error_reporting import report_exception

try:
    # Some operation that might fail
    result = risky_operation()
except Exception as e:
    report_exception("my_function", "performing risky operation", e)
```

### Device Error Reporting

```python
from error_reporting import report_device_error

try:
    motor.run(500)
except Exception as e:
    report_device_error("left_motor", "start_motor", e, "Port.A")
```

### Controller Error Reporting

```python
from error_reporting import report_controller_error

try:
    controller.connect()
except Exception as e:
    report_controller_error("PS4Controller", "connect", e, "/dev/input/js0")
```

## Output Format

### Exception Output
```
EXCEPTION in my_function - performing risky operation:
Error type: ValueError
Error details: Invalid parameter provided
Location: performing risky operation
Context: Additional context if provided
```

### Device Error Output
```
DEVICE EXCEPTION - start_motor:
Error type: OSError
Error details: Motor not responding
Context: Device: left_motor | Operation: start_motor | Port: Port.A
```

### Controller Error Output
```
CONTROLLER EXCEPTION - connect:
Error type: FileNotFoundError
Error details: Controller device not found
Context: Controller: PS4Controller | Operation: connect | Path: /dev/input/js0
```

## API Reference

### `report_exception(function_name, location_description, exception, additional_context=None)`

Report a general exception with context.

- **function_name** (str): Name of the function where exception occurred
- **location_description** (str): Description of what was being attempted
- **exception** (Exception): The caught exception object
- **additional_context** (str, optional): Additional context information

### `report_device_error(device_name, operation, exception, port=None)`

Report a device-related error.

- **device_name** (str): Name of the device that failed
- **operation** (str): What operation was being performed
- **exception** (Exception): The caught exception object
- **port** (str, optional): Port information (e.g., "Port.A")

### `report_controller_error(controller_type, operation, exception, path=None)`

Report a controller-related error.

- **controller_type** (str): Type of controller (e.g., "PS4Controller")
- **operation** (str): What operation was being performed
- **exception** (Exception): The caught exception object
- **path** (str, optional): Device path information (e.g., "/dev/input/js0")

## MicroPython Compatibility

This library is specifically designed to work with EV3 MicroPython where:
- The `traceback` module is not available
- Memory and storage constraints exist
- Simple, consistent error reporting is needed

## Testing

```bash
pytest tests/
```

## License

MIT License