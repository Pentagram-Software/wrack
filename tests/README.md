#!/usr/bin/env python3

# EV3 PS4 Controlled Robot - Test Suite

A comprehensive unit test suite for the EV3 PS4 Controlled Robot project, designed to work with both desktop development environments and EV3 MicroPython.

## Overview

This test suite provides thorough coverage of all core robot control systems, using mock objects to simulate EV3 hardware components. This allows for rapid development and testing on desktop systems without requiring actual EV3 hardware.

## Test Structure

### Test Files

- **`test_device_manager.py`** - Tests for the `DeviceManager` class
  - Device initialization and management
  - Safe device operations and error handling
  - Device availability checking
  - Fallback device mechanisms

- **`test_drive_system.py`** - Tests for the `DriveSystem` abstract base class
  - Abstract method enforcement
  - Interface compliance verification
  - Parameter validation

- **`test_tank_drive_system.py`** - Tests for the `TankDriveSystem` class  
  - Joystick control (forward, backward, turning)
  - Direct motor control methods
  - Steering sensitivity
  - Drift maneuvers
  - Speed validation and clamping

- **`test_turret.py`** - Tests for the `Turret` class
  - Speed-based control with deadzone filtering
  - Positional control and angle mapping
  - Angle limit enforcement
  - Turret homing functionality

- **`test_event_handler.py`** - Tests for the `EventHandler` class
  - Event registration and callback management
  - Event triggering and callback execution
  - Multiple callbacks per event
  - Callback execution order and parameters
  - Exception handling in callbacks
  - Lambda and method callbacks
  - Instance isolation

### Support Files

- **`conftest.py`** - Pytest configuration and shared fixtures
  - Global mock setup for pybricks modules
  - Device manager fixtures with pre-configured mock devices
  - Reusable test fixtures

- **`mock_ev3_devices.py`** - Mock implementations of EV3 hardware
  - `MockMotor` - Simulates EV3 motors with speed/angle tracking
  - `MockSensor` classes - Simulates various EV3 sensors
  - `MockPort`, `MockStop`, `MockDirection` - Parameter enums

- **`run_pytest.py`** - Modern test runner with coverage
  - Comprehensive test execution with coverage reporting
  - Support for running specific tests
  - File watching for development
  - HTML coverage report generation

## Mock Framework

The test suite uses a comprehensive mock framework that simulates EV3 hardware:

### MockMotor Features
- Speed and rotation tracking (`_speed`, `_angle`, `_running`)
- Method simulation (`run()`, `stop()`, `run_target()`, `reset_angle()`)
- State persistence across test calls
- Exception handling simulation

### MockSensor Features
- Simulated sensor readings
- Port assignment tracking
- Configurable return values for testing various scenarios

### Global Module Mocking
The `conftest.py` automatically mocks all pybricks modules:
- `pybricks.ev3devices` (Motor, sensors)
- `pybricks.parameters` (Port, Stop, Direction)
- `pybricks.tools` (wait function)
- `pybricks.hubs` (EV3Brick with speaker)

## Running Tests

### Prerequisites

Install the required test dependencies:

```bash
pip install -r requirements-test.txt
```

### Command Line Options

#### Run All Tests (Recommended)
```bash
# Using the modern pytest runner (includes coverage)
python3 tests/run_pytest.py

# Direct pytest (basic)
python3 -m pytest tests/ --verbose
```

#### Run Specific Test Files
```bash
# Using the runner
python3 tests/run_pytest.py test_turret

# Direct pytest
python3 -m pytest tests/test_turret.py --verbose
```

#### Run with File Watching (Development)
```bash
python3 tests/run_pytest.py --watch
```

#### Run with Coverage Only
```bash
python3 -m pytest tests/ --cov=. --cov-report=html:htmlcov --cov-report=term-missing
```

### Coverage Reports

The test runner generates comprehensive coverage reports:

- **Terminal Output**: Shows line-by-line coverage during test run
- **HTML Report**: Detailed coverage report at `htmlcov/index.html`
- **XML Report**: Machine-readable coverage data for CI/CD

Coverage excludes test files, mock files, and external dependencies as configured in `pytest.ini`.

## Test Configuration

### pytest.ini
- Test discovery patterns
- Coverage configuration  
- Output formatting
- Warning filters
- Minimum coverage thresholds (85%)

### requirements-test.txt
- `pytest>=7.0.0` - Modern testing framework
- `pytest-cov>=4.0.0` - Coverage reporting
- `pytest-mock>=3.10.0` - Enhanced mocking capabilities
- `pytest-xdist>=3.0.0` - Parallel test execution

## Benefits

### Development Efficiency
- **Fast Execution**: Desktop testing without EV3 hardware transfer
- **Comprehensive Coverage**: 112+ tests covering all major functionality
- **Immediate Feedback**: Tests complete in under 0.1 seconds
- **Parallel Development**: Multiple developers can work without hardware conflicts

### Code Quality Assurance
- **Regression Prevention**: Catch breaking changes before deployment
- **Interface Validation**: Ensure abstract base classes are properly implemented
- **Edge Case Testing**: Validate error handling and boundary conditions
- **Documentation**: Tests serve as executable specifications

### CI/CD Integration
- **Automated Testing**: Run tests on every commit
- **Coverage Tracking**: Monitor test coverage over time  
- **Cross-Platform**: Tests work on any system with Python
- **Dependency Validation**: Verify compatibility with different environments

## Advanced Features

### Parameterized Tests
Many tests use `@pytest.mark.parametrize` for efficient multi-value testing:

```python
@pytest.mark.parametrize("x_axis,expected_speed", [
    (60, 216),    # 60% of 360 = 216°/s
    (-80, -288),  # -80% of 360 = -288°/s  
    (100, 360),   # 100% of 360 = 360°/s (max)
    (-100, -360), # -100% of 360 = -360°/s (max)
])
def test_speed_control_movement_outside_deadzone(self, x_axis, expected_speed):
    self.turret.speed_control(x_axis, 0)
    assert self.mock_motor._speed == expected_speed
    assert self.mock_motor._running == True
```

### Fixture Management
Shared fixtures provide consistent test environments:

```python
@pytest.fixture
def device_manager_with_motors(device_manager):
    """Provide a DeviceManager with mock motors already set up"""
    left_motor = MockMotor(MockPort.A)
    right_motor = MockMotor(MockPort.D)
    
    device_manager.devices["drive_L_motor"] = left_motor
    device_manager.devices["drive_R_motor"] = right_motor
    device_manager.available_devices.extend(["drive_L_motor", "drive_R_motor"])
    
    return device_manager, left_motor, right_motor
```

### Error Simulation
Tests validate graceful error handling:

```python
def test_try_init_device_failure(self):
    """Test device initialization failure"""
    class FailingDevice:
        def __init__(self, port):
            raise Exception("Device not found")
    
    device = self.device_manager.try_init_device(FailingDevice, MockPort.A, "failing_device")
    
    assert device is None
    assert self.device_manager.devices["failing_device"] is None
    assert "failing_device" not in self.device_manager.available_devices
    assert "failing_device" in self.device_manager.missing_devices
```

## Integration with Development Workflow

### Pre-Commit Testing
Run tests before committing changes:
```bash
python3 tests/run_pytest.py && git commit -m "Your commit message"
```

### IDE Integration
Most modern IDEs (VSCode, PyCharm, etc.) can automatically discover and run pytest tests with full debugging support.

### Continuous Integration
The test suite is designed for easy CI/CD integration:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install -r requirements-test.txt
    python3 tests/run_pytest.py
```

## Adding New Tests

When adding new functionality to the robot control system:

1. **Create test file**: Follow naming pattern `test_<module_name>.py`
2. **Use fixtures**: Leverage existing fixtures for device setup
3. **Mock dependencies**: Add new mock classes to `mock_ev3_devices.py` if needed
4. **Test edge cases**: Include error conditions and boundary value testing
5. **Update documentation**: Add test descriptions to this README

This comprehensive test suite ensures that the EV3 PS4 Controlled Robot maintains high code quality and reliability throughout development. 