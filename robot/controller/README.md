# EV3 PS4 Controlled Robot

A comprehensive LEGO Mindstorms EV3 robot control system with PS4 controller support, network remote control via TCP/IP, and Google Cloud Functions integration.

## 🎯 Features

- **Dual Control Modes**: PS4 controller (Bluetooth) and network remote control (TCP/IP)
- **Tank Drive System**: Differential drive with joystick control
- **Turret Control**: Pan/tilt camera/sensor mount with speed control
- **Terrain Scanning**: Automated 360° terrain mapping using ultrasonic and gyro sensors
- **Cloud Integration**: Google Cloud Functions API for remote robot control
- **Comprehensive Status API**: Real-time sensor readings, motor positions, battery, CPU, and network info
- **Graceful Device Management**: Automatic detection and handling of missing/failed devices
- **Hot-Plug Support**: Background port monitor detects disconnected or newly connected devices within 1-2 s; subsystems self-heal without restarting the program
- **Audio Feedback**: Text-to-speech and programmable beep signals

## 📋 Table of Contents

- [Architecture](#architecture)
- [Hardware Setup](#hardware-setup)
- [Software Architecture](#software-architecture)
- [Communication Protocols](#communication-protocols)
- [API Reference](#api-reference)
- [Installation](#installation)
- [Usage](#usage)
- [Development](#development)

## 🏗 Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Control Inputs                           │
├──────────────────────┬──────────────────────────────────────────┤
│   PS4 Controller     │    Network Remote (TCP/IP)               │
│   (Bluetooth)        │    - Direct TCP Socket                   │
│                      │    - Google Cloud Functions              │
└──────────┬───────────┴────────────────┬─────────────────────────┘
           │                            │
           v                            v
    ┌──────────────────────────────────────────────┐
    │         EV3 Brick (main.py)                  │
    │  ┌────────────────────────────────────────┐  │
    │  │      Event-Driven Architecture         │  │
    │  │  - PS4Controller (Thread)              │  │
    │  │  - RemoteController (Thread)           │  │
    │  │  - EventHandler (Base Class)           │  │
    │  └────────────────────────────────────────┘  │
    │  ┌────────────────────────────────────────┐  │
    │  │      Device Manager                    │  │
    │  │  - Graceful device initialization      │  │
    │  │  - Safe device operations              │  │
    │  │  - Battery & system monitoring         │  │
    │  └────────────────────────────────────────┘  │
    │  ┌────────────────────────────────────────┐  │
    │  │      Drive Systems                     │  │
    │  │  - TankDriveSystem                     │  │
    │  │  - Turret                              │  │
    │  │  - TerrainScanner (optional)           │  │
    │  └────────────────────────────────────────┘  │
    └──────────────────┬───────────────────────────┘
                       │
           ┌───────────┴───────────┐
           v                       v
    ┌─────────────┐         ┌─────────────┐
    │   Motors    │         │   Sensors   │
    ├─────────────┤         ├─────────────┤
    │ Port A: L   │         │ S1: Camera  │
    │ Port D: R   │         │ S2: Ultra   │
    │ Port C: Tur │         │ S3: Gyro    │
    └─────────────┘         └─────────────┘
```

## 🔧 Hardware Setup

### Required Components

- **LEGO Mindstorms EV3 Brick** (running ev3dev or Pybricks)
- **Motors**:
  - Port A: Left drive motor
  - Port D: Right drive motor
  - Port C: Turret motor (optional)
- **Sensors**:
  - Port S2: Ultrasonic sensor
  - Port S3: Gyro sensor
  - Port S1: Pixy2 camera (optional)
- **PS4 Controller** (optional, for Bluetooth control)

### Network Setup

1. Connect EV3 to WiFi or Ethernet
2. Note the EV3's IP address (visible in device settings)
3. Default TCP port: `27700`

## 🌐 Communication Protocols

### TCP/IP Network Protocol

**Connection**: TCP socket on port `27700`

**Message Format**: JSON or plain text, newline-terminated (`\n`)

**Flow**:
1. Client connects to EV3 IP:27700
2. EV3 sends welcome message (plain text)
3. Client sends commands (JSON or text)
4. EV3 responds with JSON

### Command Examples

#### JSON Commands
```json
{"action": "move", "direction": "forward", "speed": 500}
{"action": "battery"}
{"action": "status"}
{"action": "beep", "frequency": 1000, "duration": 300}
```

#### Text Commands
```
forward
battery
status
```

## 📚 API Reference

### Movement Commands
- `forward`, `backward`, `left`, `right`, `stop`
- `move` - with direction, speed, duration
- `joystick` - direct axis control

### System Commands
- `battery` - Get battery status
- `status` / `get_status` - Comprehensive system status
- `beep` - Play sound (frequency, duration)
- `speak` - Text-to-speech

## 🚀 Installation

```bash
# Copy to EV3
scp -r ev3PS4Controlled/ robot@<EV3_IP>:/home/robot/

# Run on EV3
ssh robot@<EV3_IP>
cd /home/robot/ev3PS4Controlled
python3 main.py
```

## 📖 Usage

### Network Control
```bash
# Using netcat
printf '{"action":"battery"}\n' | nc <EV3_IP> 27700
```

## 📡 Telemetry

The `telemetry/` module provides buffered, thread-safe event collection for the EV3 controller.

### TelemetryCollector

`TelemetryCollector` builds standard event envelopes and stores them in a bounded in-memory
FIFO queue (max 500 events by default). When the buffer is full, the oldest event is dropped
first (FIFO drop). An optional disk spill path can be configured so dropped events are written
to a `.jsonl` file instead of being lost.

```python
from telemetry.collector import TelemetryCollector

collector = TelemetryCollector(
    source="ev3",
    session_id="session-abc",   # optional — injected into every event envelope
    device_id="ev3-unit-1",     # optional — injected into every event envelope
    max_buffer=500,              # max events held in memory (FIFO drop on overflow)
    disk_spill_path="/tmp/telemetry_overflow.jsonl",  # optional overflow file
)

# Collect a battery status event
collector.collect("battery_status", voltage_mv=7200, percentage=85.0)

# Collect a command event
collector.collect("command_received", command="forward", controller_type="ps4")

# Drain and send the buffer (e.g. to telemetryIngestion cloud function)
events = collector.flush()  # returns list[dict], clears buffer

# Non-destructive snapshot
snapshot = collector.get_events(limit=10)

# Stats
print(collector.size())          # current buffer size
print(collector.dropped_count)   # total events dropped due to overflow
print(collector.invalid_count)   # total events rejected by validation
```

Each collected event envelope includes:

| Field | Description |
|---|---|
| `event_id` | UUID v4, auto-generated |
| `event_type` | As passed to `collect()` |
| `source` | Configured source (default `"ev3"`) |
| `timestamp` | ISO 8601 UTC with milliseconds, e.g. `2026-01-01T12:00:00.000Z` |
| `payload` | Dict of `**data` kwargs passed to `collect()` |
| `session_id` | Injected if configured |
| `device_id` | Injected if configured |

Events are validated against the shared telemetry schemas before buffering. Invalid events are
silently discarded and counted in `invalid_count`. Pass `validate=False` to skip validation.

### Running telemetry tests

```bash
cd robot/controller
python -m pytest telemetry/tests/ -v
```

## 🧪 Development

```bash
# Run tests
python3 tests/run_pytest.py
```

## 📝 License

Educational and hobbyist use.

---

**Happy Building! 🤖**
