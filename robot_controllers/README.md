# Robot Controllers Library

A comprehensive library providing controller interfaces for robotics applications. Supports PS4 controllers and network remote control via TCP/IP.

## Features

- **PS4 Controller Support**: Full PS4 DualShock controller integration
- **Network Remote Control**: TCP/IP based remote control with JSON commands
- **Event-Driven Architecture**: Built on event handlers for responsive control
- **Threaded Operation**: Non-blocking controller operation
- **EV3 MicroPython Compatible**: Designed for LEGO EV3 environments
- **Error Handling**: Robust error reporting and recovery
- **Multiple Input Support**: Handle multiple controllers simultaneously

## Installation

```bash
pip install -e .
```

## Dependencies

- `event-handler>=1.0.0` - For event handling capabilities
- `error-reporting>=1.0.0` - For error reporting

## Usage

### PS4 Controller

```python
from robot_controllers import PS4Controller

# Initialize controller
controller = PS4Controller()

# Register event callbacks
def on_move(sender):
    print(f"Joystick: L({sender.l_left}, {sender.l_forward}) R({sender.r_left}, {sender.r_forward})")

def on_button_press(sender):
    print("Cross button pressed!")

def on_quit(sender):
    print("Stopping controller...")
    sender.stop()

# Register callbacks
controller.onLeftJoystickMove(on_move)
controller.onRightJoystickMove(on_move) 
controller.onCrossButton(on_button_press)
controller.onOptionsButton(on_quit)

# Connect and start
if controller.connect():
    controller.start()
    print("PS4 controller ready!")
else:
    print("PS4 controller not found")
```

### Network Remote Controller

```python
from robot_controllers import RemoteController

# Initialize remote controller
remote = RemoteController()

# Register command callbacks
def on_forward(sender):
    print("Moving forward")

def on_stop(sender):
    print("Stopping")

def on_joystick(sender):
    print(f"Joystick control: L({sender.l_left}, {sender.l_forward})")

# Register callbacks
remote.onForward(on_forward)
remote.onStop(on_stop)
remote.onLeftJoystick(on_joystick)

# Start network server
remote.start()
print("Network controller listening on port 27700")
```

### Advanced Usage - Multiple Controllers

```python
from robot_controllers import PS4Controller, RemoteController

# Initialize both controllers
ps4 = PS4Controller()
remote = RemoteController()

def unified_move_handler(sender):
    # Handle movement from any controller
    print(f"Movement: L({sender.l_left}, {sender.l_forward})")

def unified_stop_handler(sender):
    print("Stop command received")

# Register same handlers for both controllers
ps4.onLeftJoystickMove(unified_move_handler)
remote.onLeftJoystick(unified_move_handler)

ps4.onOptionsButton(unified_stop_handler)
remote.onStop(unified_stop_handler)

# Start both controllers
if ps4.connect():
    ps4.start()

remote.start()
```

## PS4 Controller API

### Events

- `onLeftJoystickMove(callback)` - Left joystick movement
- `onRightJoystickMove(callback)` - Right joystick movement
- `onCrossButton(callback)` - Cross (X) button press
- `onCircleButton(callback)` - Circle button press
- `onTriangleButton(callback)` - Triangle button press
- `onSquareButton(callback)` - Square button press
- `onOptionsButton(callback)` - Options button press
- `onLeftArrowPressed(callback)` - D-pad left press
- `onRightArrowPressed(callback)` - D-pad right press
- `onUpArrowPressed(callback)` - D-pad up press
- `onDownArrowPressed(callback)` - D-pad down press
- `onL1Button(callback)` - L1 button press
- `onR1Button(callback)` - R1 button press

### Methods

- `connect()` - Connect to PS4 controller (returns True/False)
- `is_connected()` - Check connection status
- `start()` - Start controller thread
- `stop()` - Stop controller thread

### Properties

- `l_left`, `l_forward` - Left joystick values (-1000 to 1000)
- `r_left`, `r_forward` - Right joystick values (-1000 to 1000)
- `connected` - Connection status

## Network Remote Controller API

### Events

- `onForward(callback)` - Forward movement command
- `onBackward(callback)` - Backward movement command
- `onLeft(callback)` - Left turn command
- `onRight(callback)` - Right turn command
- `onStop(callback)` - Stop command
- `onFire(callback)` - Fire/action command
- `onLeftJoystick(callback)` - Left joystick data
- `onRightJoystick(callback)` - Right joystick data
- `onCameraLeft(callback)` - Camera left command
- `onCameraRight(callback)` - Camera right command
- `onTurretLeft(callback)` - Turret left command
- `onTurretRight(callback)` - Turret right command
- `onQuit(callback)` - Quit command

### Methods

- `start()` - Start network server
- `stop()` - Stop network server

### Network Commands

#### Simple Text Commands
```
forward
backward
left
right
stop
fire
quit
```

#### JSON Commands
```json
{"action": "forward", "speed": 500}
{"action": "move", "direction": "left", "speed": 1000}
{"action": "joystick", "l_left": -200, "l_forward": 800}
{"action": "turret", "direction": "left", "speed": 150, "duration": 2}
{"action": "stop"}
```

## Constants

- `MIN_JOYSTICK_MOVE = 100` - Minimum joystick movement threshold

## Error Handling

Both controllers include comprehensive error handling:

- Connection failures
- Device access issues
- Network communication errors
- Hardware disconnection

Errors are reported using the integrated error reporting system.

## Threading

Both controllers run in separate threads for non-blocking operation:
- PS4 controller continuously polls for input events
- Remote controller listens for network connections
- Main application remains responsive

## EV3 MicroPython Compatibility

Designed specifically for EV3 MicroPython:
- Minimal memory footprint
- No heavy dependencies
- Binary event parsing for PS4 controller
- TCP socket handling for network control

## Testing

```bash
pytest tests/
```

## Hardware Requirements

### PS4 Controller
- PS4 DualShock controller
- Bluetooth connection to EV3
- Linux input device support

### Network Remote Controller
- Network connection (WiFi/Ethernet)
- TCP/IP connectivity
- Port 27700 available

## License

MIT License