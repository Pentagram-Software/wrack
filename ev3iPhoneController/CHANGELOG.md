# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Sensor data display (ultrasonic, color, gyro)
- Command history and macros
- Multi-robot support
- Offline mode with local Bluetooth connectivity
- Haptic feedback for controls
- Record and replay movement sequences
- Apple Watch companion app

## [1.0.0] - 2025-07-12

### Added
- Initial release
- Remote robot control via cloud function
- Real-time video streaming from robot camera
- Vehicle movement controls (forward, backward, left, right, stop)
- Turret rotation controls
- Joystick mode for direct motor control
- Adaptive UI supporting portrait and landscape orientations
- Connection status monitoring
- Speed control settings
- Dark mode interface
- Error handling and reporting
- Async/await based network communication
- SwiftUI-based user interface

### Features
- Movement Controls
  - Forward/backward movement with adjustable speed
  - Left/right turning
  - Emergency stop button
  - Joystick control for independent motor control
  
- Turret Controls
  - Rotate left and right
  - Adjustable rotation speed and duration
  - Independent turret stop

- User Interface
  - Portrait and landscape layouts
  - Live video feed
  - Status indicators (connection, battery, signal)
  - Real-time control feedback
  - Settings menu

- Technical
  - REST API communication with JSON encoding
  - Configurable timeouts and retry logic
  - Error handling and recovery
  - Connection state management

[Unreleased]: https://github.com/yourusername/ev3iPhoneController/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/yourusername/ev3iPhoneController/releases/tag/v1.0.0
