# Event Handler Library

A simple, reusable event handling system for Python applications. This library provides a base class that can be inherited to add event functionality to any class.

## Features

- Simple event registration and triggering
- Multiple callbacks per event
- Ordered callback execution
- No external dependencies
- Lightweight and fast
- Thread-safe event handling

## Installation

```bash
pip install -e .
```

## Usage

### Basic Usage

```python
from event_handler import EventHandler

class MyClass(EventHandler):
    def __init__(self):
        super().__init__()
    
    def do_something(self):
        # Trigger an event
        self.trigger("something_happened")

# Create instance and register callback
obj = MyClass()

def my_callback(sender):
    print(f"Event triggered by {sender}")

obj.on("something_happened", my_callback)
obj.do_something()  # Will call my_callback
```

### Multiple Callbacks

```python
def callback1(sender):
    print("Callback 1")

def callback2(sender):
    print("Callback 2")

obj.on("my_event", callback1)
obj.on("my_event", callback2)
obj.trigger("my_event")  # Both callbacks will be called in order
```

## API Reference

### `EventHandler.on(event_name, callback)`

Register a callback function for an event.

- **event_name** (str): Name of the event
- **callback** (function): Function to call when event is triggered. Must accept one parameter (sender).

### `EventHandler.trigger(event_name)`

Trigger all callbacks registered for an event.

- **event_name** (str): Name of the event to trigger

## Testing

```bash
pytest tests/
```

## License

MIT License