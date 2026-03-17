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

## 🧪 Development

```bash
# Run tests
python3 tests/run_pytest.py
```

## 📝 License

Educational and hobbyist use.

---

**Happy Building! 🤖**
