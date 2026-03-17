# EV3 Devices Library

A comprehensive device management and drive system library for LEGO MINDSTORMS EV3 robots. Provides robust device initialization, safe operation, and multiple drive system implementations.

## Features

- **Device Management**: Centralized device initialization with graceful error handling
- **Safe Operations**: Robust device access with automatic error recovery
- **Drive Systems**: Multiple drive implementations (tank, car-style)
- **Turret Control**: Camera/weapon turret management
- **Mock Support**: Testing support with mock devices
- **EV3 MicroPython**: Optimized for EV3 hardware constraints

## Installation

```bash
pip install -e .
```

## Dependencies

- `error-reporting>=1.0.0` - For error handling
- `pybricks` - EV3 MicroPython framework (EV3-only)

## Usage

### Device Manager

```python
from ev3_devices import DeviceManager
from pybricks.ev3devices import Motor
from pybricks.parameters import Port

# Initialize device manager
device_manager = DeviceManager()

# Try to initialize devices with graceful error handling
left_motor = device_manager.try_init_device(Motor, Port.A, "left_motor")
right_motor = device_manager.try_init_device(Motor, Port.D, "right_motor")

# Check device availability
if device_manager.is_device_available("left_motor"):
    print("Left motor is ready")

# Safe device operations
device_manager.safe_device_call("left_motor", "run", 500)
device_manager.safe_device_call("left_motor", "stop")

# Get device status
device_manager.print_device_status()
```

### Tank Drive System

```python
from ev3_devices import TankDriveSystem, DeviceManager

# Initialize with device manager
device_manager = DeviceManager()
tank_drive = TankDriveSystem(device_manager)
tank_drive.initialize()

# Basic movement
tank_drive.move_forward(1000)    # Full speed forward
tank_drive.move_backward(500)    # Half speed backward
tank_drive.drift_left(800)       # Turn left while moving
tank_drive.drift_right(800)      # Turn right while moving
tank_drive.stop()                # Stop all movement

# Joystick control
tank_drive.joystick_control(forward_speed=800, turn_speed=-300)

# Advanced movement
tank_drive.pivot_turn_left(500, duration=2.0)   # Pivot turn for 2 seconds
tank_drive.pivot_turn_right(500, duration=1.5)  # Pivot turn for 1.5 seconds
```

### Car Drive System

```python
from ev3_devices import CarDriveSystem, DeviceManager

# Initialize car-style driving
device_manager = DeviceManager()
car_drive = CarDriveSystem(device_manager)
car_drive.initialize()

# Car-style movement
car_drive.drive_forward(800)     # Drive forward
car_drive.drive_backward(500)    # Drive backward
car_drive.steer_left(45)         # Steer left 45 degrees
car_drive.steer_right(30)        # Steer right 30 degrees
car_drive.stop()                 # Stop and center steering
```

### Turret Control

```python
from ev3_devices import Turret, DeviceManager

# Initialize turret
device_manager = DeviceManager()
turret = Turret(device_manager)

# Basic turret movement
turret.move_left(500)            # Rotate left
turret.move_right(500)           # Rotate right
turret.stop()                    # Stop rotation

# Speed control (like joystick input)
turret.speed_control(x_axis=-50, y_axis=0)  # Rotate left at 50% speed
turret.speed_control(x_axis=75, y_axis=0)   # Rotate right at 75% speed
turret.speed_control(x_axis=0, y_axis=0)    # Stop

# Position control
turret.move_to_angle(90)         # Move to 90 degrees
turret.center()                  # Return to center position
```

## API Reference

### DeviceManager

#### Methods

- `try_init_device(device_class, *args, device_name)` - Safely initialize device
- `is_device_available(device_name)` - Check if device exists
- `are_devices_available(device_names)` - Check multiple devices
- `safe_device_call(device_name, method_name, *args)` - Safe method call
- `safe_device_operation(device_name, operation_name, func, *args)` - Safe complex operation
- `get_device_summary()` - Get device availability summary
- `print_device_status()` - Print device status report
- `cleanup()` - Clean up all devices

### DriveSystem (Base Class)

#### Methods

- `initialize()` - Initialize drive system
- `stop()` - Stop all movement
- `is_initialized()` - Check initialization status

### TankDriveSystem

#### Methods

- `move_forward(speed)` - Move forward at speed
- `move_backward(speed)` - Move backward at speed
- `drift_left(speed)` - Turn left while moving
- `drift_right(speed)` - Turn right while moving
- `pivot_turn_left(speed, duration=None)` - Pivot left
- `pivot_turn_right(speed, duration=None)` - Pivot right
- `joystick_control(forward_speed, turn_speed)` - Joystick-style control
- `stop()` - Stop all motors

### CarDriveSystem

#### Methods

- `drive_forward(speed)` - Drive forward
- `drive_backward(speed)` - Drive backward
- `steer_left(angle)` - Steer left by angle
- `steer_right(angle)` - Steer right by angle
- `center_steering()` - Center steering wheel
- `stop()` - Stop driving and center steering

### Turret

#### Methods

- `move_left(speed)` - Rotate left at speed
- `move_right(speed)` - Rotate right at speed
- `speed_control(x_axis, y_axis)` - Joystick-style speed control
- `move_to_angle(angle)` - Move to specific angle
- `center()` - Return to center position
- `stop()` - Stop rotation

## Device Configuration

### Motor Ports

Default motor port assignments:

- **Tank Drive**: Port A (left), Port D (right)
- **Car Drive**: Port A (left drive), Port D (right drive), Port B (steering)
- **Turret**: Port C

### Sensor Ports

Supported sensors:

- **Ultrasonic**: Port S1-S4
- **Color**: Port S1-S4
- **Touch**: Port S1-S4
- **Gyro**: Port S1-S4

## Error Handling

The library provides comprehensive error handling:

- **Device Initialization**: Graceful handling of missing devices
- **Operation Errors**: Safe method calls with error reporting
- **Hardware Failures**: Automatic recovery and mock object substitution
- **Connection Issues**: Robust device access patterns

All errors are reported using the integrated error reporting system.

## Testing

```bash
pytest tests/
```

### Mock Devices

For testing without hardware:

```python
from ev3_devices.tests.mock_ev3_devices import MockMotor, MockPort

# Use mock devices for testing
mock_motor = MockMotor(MockPort.A)
mock_motor.run(500)
mock_motor.stop()
```

## EV3 MicroPython Compatibility

Designed specifically for EV3 MicroPython:

- **Memory Efficient**: Minimal memory footprint
- **Resource Management**: Proper device cleanup
- **Error Resilience**: Graceful degradation when devices unavailable
- **Thread Safe**: Safe for concurrent operations

## Hardware Requirements

- LEGO MINDSTORMS EV3 Brick
- EV3 Motors (Medium/Large)
- EV3 Sensors (optional)
- EV3 MicroPython firmware

## Examples

### Complete Robot Setup

```python
from ev3_devices import DeviceManager, TankDriveSystem, Turret
from pybricks.ev3devices import Motor, UltrasonicSensor
from pybricks.parameters import Port

# Initialize everything
device_manager = DeviceManager()

# Set up motors
device_manager.try_init_device(Motor, Port.A, "drive_L_motor")
device_manager.try_init_device(Motor, Port.D, "drive_R_motor") 
device_manager.try_init_device(Motor, Port.C, "turret_motor")

# Set up sensors
device_manager.try_init_device(UltrasonicSensor, Port.S2, "us_sensor")

# Initialize drive systems
tank_drive = TankDriveSystem(device_manager)
tank_drive.initialize()

turret = Turret(device_manager)

# Print status
device_manager.print_device_status()

# Use the robot
tank_drive.move_forward(800)
turret.move_left(300)
```

## License

MIT License