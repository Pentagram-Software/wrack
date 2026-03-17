# Pixy Camera Library

A Python library for interfacing with the Pixy2 camera on EV3 MicroPython. Provides event-driven block detection and camera control capabilities.

## Features

- Event-driven block detection using EventHandler
- Threaded camera operation for real-time detection
- Light control for the Pixy2 camera
- Easy callback registration for block detection events
- EV3 MicroPython compatible
- No blocking operations - runs in background thread

## Installation

```bash
pip install -e .
```

## Dependencies

- `event-handler>=1.0.0` - For event handling capabilities

## Usage

### Basic Usage

```python
from pixy_camera import Pixy2Camera

# Initialize camera
camera = Pixy2Camera(port=1)

# Register callback for block detection
def on_block_detected(sender):
    print(f"Block detected! Blocks: {sender.blocks}")

camera.onBlockDetected(on_block_detected)

# Start camera thread
camera.start()

# Control camera light
camera.light(True)   # Turn on
camera.light(False)  # Turn off

# Stop camera
camera.stopped = True
camera.join()
camera.close()
```

### Advanced Usage with Multiple Callbacks

```python
from pixy_camera import Pixy2Camera

camera = Pixy2Camera()

def track_largest_block(sender):
    if sender.blocks:
        largest = max(sender.blocks, key=lambda b: b.get('width', 0) * b.get('height', 0))
        print(f"Largest block at ({largest.get('x', 0)}, {largest.get('y', 0)})")

def count_blocks(sender):
    if sender.blocks:
        print(f"Total blocks detected: {len(sender.blocks)}")

# Register multiple callbacks
camera.onBlockDetected(track_largest_block)
camera.onBlockDetected(count_blocks)

camera.start()
# Camera will now trigger both callbacks when blocks are detected
```

### Integration with EV3 Robot

```python
from pixy_camera import Pixy2Camera
from pybricks.hubs import EV3Brick

ev3 = EV3Brick()
camera = Pixy2Camera()

def react_to_block(sender):
    if sender.blocks:
        ev3.speaker.beep()  # Beep when block detected
        sender.light(True)  # Flash light
        
camera.onBlockDetected(react_to_block)
camera.start()

# Robot continues other operations while camera runs in background
```

## API Reference

### `Pixy2Camera(port=1)`

Initialize a new Pixy2Camera instance.

- **port** (int): I2C port number (default: 1)

### Methods

#### `onBlockDetected(callback)`

Register a callback function to be called when blocks are detected.

- **callback** (function): Function to call when blocks are detected. Must accept one parameter (sender).

#### `light(on)`

Control the camera's LED light.

- **on** (bool): True to turn light on, False to turn off

#### `start()`

Start the camera detection thread (inherited from threading.Thread).

#### `close()`

Close the camera connection and release resources.

### Properties

#### `blocks`

List of currently detected blocks. Updated automatically during detection loop.

#### `stopped`

Boolean flag to stop the camera detection thread. Set to True to stop.

## Block Detection

The camera continuously scans for blocks in a background thread. When blocks are detected:

1. The `blocks` property is updated with detected block information
2. All registered callbacks are triggered with the camera instance as parameter
3. Each block contains position and size information

## Threading

The camera runs in a separate thread to avoid blocking the main program. This allows:
- Real-time block detection
- Concurrent robot operations
- Responsive camera control

## MicroPython Compatibility

This library is designed for EV3 MicroPython:
- Uses only standard Python threading
- No heavy dependencies
- Efficient memory usage
- Compatible with EV3 hardware constraints

## Error Handling

The library handles common camera errors gracefully:
- Connection failures
- I2C communication errors
- Hardware initialization issues

## Testing

```bash
pytest tests/
```

## Hardware Requirements

- LEGO EV3 Brick with MicroPython
- Pixy2 Camera
- I2C connection between EV3 and Pixy2

## License

MIT License