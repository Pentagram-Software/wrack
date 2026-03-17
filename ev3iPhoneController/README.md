# EV3 iPhone Controller

A SwiftUI-based iOS application for remotely controlling a LEGO Mindstorms EV3 robot over the internet. The app provides real-time video streaming, vehicle movement controls, and turret control through an intuitive interface.

<img src="https://img.shields.io/badge/iOS-15.0+-blue.svg" alt="iOS 15.0+">
<img src="https://img.shields.io/badge/Swift-5.9-orange.svg" alt="Swift 5.9">
<img src="https://img.shields.io/badge/SwiftUI-3.0-green.svg" alt="SwiftUI 3.0">

## Features

### 🚗 Vehicle Control
- **Movement Controls**: Forward, backward, left turn, and right turn
- **Joystick Mode**: Direct control of left and right motors independently
- **Speed Control**: Adjustable speed settings for precise control
- **Emergency Stop**: Quick-access stop button

### 🎥 Live Video Streaming
- Real-time camera feed from the robot
- Support for both portrait and landscape orientations
- Adaptive layout that optimizes for screen size

### 🔧 Turret Control
- Rotate turret left and right
- Adjustable rotation speed and duration
- Independent turret motor control

### 📱 User Interface
- **Adaptive Layout**: Optimized for both portrait and landscape orientations
- **Dark Mode**: Sleek dark interface for comfortable viewing
- **Status Indicators**: Connection status, battery level, and signal strength
- **Real-time Feedback**: Visual indicators for active controls

## Screenshots

_Add screenshots here showing the app in portrait and landscape modes_

## Requirements

- iOS 15.0 or later
- iPadOS 15.0 or later
- Xcode 14.0 or later
- Swift 5.9 or later
- Active internet connection
- EV3 robot with internet connectivity (via cloud function)

## Installation

### Clone the Repository

```bash
git clone https://github.com/yourusername/ev3iPhoneController.git
cd ev3iPhoneController
```

### Configure the App

1. Open `Config.swift`
2. Update the cloud function URL:
   ```swift
   static let cloudFunctionURL = "YOUR_CLOUD_FUNCTION_URL"
   ```
3. Replace the API key with your actual key:
   ```swift
   static let apiKey = "YOUR_API_KEY_HERE"
   ```

### Build and Run

1. Open `ev3iPhoneController.xcodeproj` in Xcode
2. Select your target device or simulator
3. Press `⌘ + R` to build and run

## Architecture

### Core Components

- **RobotController**: Main controller class managing all robot operations
  - Async/await based network operations
  - Connection status monitoring
  - Command encoding and response handling

- **ContentView**: Primary UI implementing adaptive layouts
  - Portrait and landscape mode support
  - Responsive controls and status display

- **VideoStreamView**: Live video streaming from robot camera
  - WebKit-based video player
  - Adaptive frame sizing

- **Config**: Centralized configuration for URLs, API keys, and control parameters

### Communication Protocol

The app communicates with the robot through a REST API using JSON-encoded commands:

```swift
{
  "command": "forward",
  "params": {
    "speed": 500,
    "duration": 0
  }
}
```

## Available Commands

| Command | Description | Parameters |
|---------|-------------|------------|
| `forward` | Move robot forward | `speed`: Int, `duration`: Double |
| `backward` | Move robot backward | `speed`: Int, `duration`: Double |
| `left` | Turn left | `speed`: Int, `duration`: Double |
| `right` | Turn right | `speed`: Int, `duration`: Double |
| `stop` | Stop all movement | None |
| `turret_left` | Rotate turret left | `speed`: Int, `duration`: Double |
| `turret_right` | Rotate turret right | `speed`: Int, `duration`: Double |
| `stop_turret` | Stop turret rotation | None |
| `joystick_control` | Direct motor control | `l_left`: Int, `l_forward`: Int, `r_left`: Int, `r_forward`: Int |
| `get_status` | Query robot status | None |

## Configuration Options

Edit `Config.swift` to customize:

```swift
// Control speeds
static let defaultTurnSpeed = 300        // Default turning speed
static let defaultMoveSpeed = 500        // Default movement speed
static let maxSpeed = 2000               // Maximum motor speed

// Turret settings
static let defaultTurretSpeed = 200      // Default turret rotation speed
static let defaultTurretDuration = 1.0   // Default rotation duration

// Network settings
static let timeoutInterval = 10.0        // Request timeout in seconds
```

## Backend Setup

This app requires a backend cloud function to relay commands to your EV3 robot. The backend should:

1. Accept POST requests with JSON-encoded robot commands
2. Authenticate using the `X-API-Key` header
3. Forward commands to the EV3 robot
4. Return a response in the format:
   ```json
   {
     "success": true,
     "message": "Command executed",
     "error": null
   }
   ```

Example backend implementations can be built using:
- Google Cloud Functions
- AWS Lambda
- Azure Functions
- Node.js/Express server

## Troubleshooting

### Connection Issues

- Verify the cloud function URL is correct
- Check that the API key matches your backend configuration
- Ensure the robot is connected to the internet
- Check firewall settings

### Video Stream Not Loading

- Verify the video stream URL in `VideoStreamView.swift`
- Check that the robot's camera is active
- Ensure network connectivity

### Controls Not Responding

- Check connection status indicator
- Review error messages in the status bar
- Verify robot is powered on and connected

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes:

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Future Enhancements

- [ ] Add sensor data display (ultrasonic, color, gyro)
- [ ] Implement command history and macros
- [ ] Add multi-robot support
- [ ] Implement offline mode with local Bluetooth connectivity
- [ ] Add haptic feedback for controls
- [ ] Record and replay movement sequences
- [ ] Add Apple Watch companion app

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with SwiftUI and modern Swift Concurrency
- LEGO Mindstorms EV3 platform
- Inspired by the robotics education community

## Contact

Created by Rafal Kuklinski

---

**Note**: This app is designed for educational and hobby purposes. Ensure proper safety measures when operating physical robots.
