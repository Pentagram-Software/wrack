# Quick Start Guide

Get up and running with EV3 iPhone Controller in minutes!

## Prerequisites

Before you begin, ensure you have:

- ✅ Mac with macOS Monterey (12.0) or later
- ✅ Xcode 14.0 or later installed
- ✅ iOS device or simulator running iOS 15.0+
- ✅ LEGO Mindstorms EV3 robot with internet connectivity
- ✅ Cloud function/backend server to relay commands

## Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/ev3iPhoneController.git
cd ev3iPhoneController
```

## Step 2: Open in Xcode

```bash
open ev3iPhoneController.xcodeproj
```

Or simply double-click the `ev3iPhoneController.xcodeproj` file.

## Step 3: Configure Your Backend

Open `Config.swift` and update the following:

```swift
struct Config {
    // Replace with your cloud function URL
    static let cloudFunctionURL = "https://your-backend-url.com/controlRobot"
    
    // Replace with your API key
    static let apiKey = "your-api-key-here"
    
    // Optional: Adjust control parameters
    static let defaultTurnSpeed = 300
    static let defaultMoveSpeed = 500
    static let maxSpeed = 2000
}
```

### Backend Requirements

Your backend should:
1. Accept POST requests with JSON payloads
2. Authenticate using `X-API-Key` header
3. Forward commands to your EV3 robot
4. Return JSON responses in this format:

```json
{
  "success": true,
  "message": "Command executed",
  "error": null
}
```

## Step 4: Update Video Stream URL (Optional)

If you have a video stream from your robot, update `VideoStreamView.swift`:

```swift
private let videoStreamURL = "http://your-robot-ip:port/video"
```

## Step 5: Build and Run

1. Select your target device (iPhone or iPad) or simulator
2. Press `⌘ + R` or click the ▶️ button
3. Wait for the build to complete
4. The app will launch automatically

## Step 6: Test the Connection

Once the app is running:

1. Check the connection indicator (circle) in the top-left corner
   - 🟢 Green = Connected
   - 🔴 Red = Disconnected
   - 🟡 Yellow = Error

2. Try a simple command like "Stop" to test connectivity

3. If successful, try movement commands

## Common Issues

### "Invalid URL" Error
- Check that `cloudFunctionURL` is correct in `Config.swift`
- Ensure the URL includes `https://`

### Connection Timeout
- Verify your backend server is running
- Check firewall settings
- Ensure your device has internet connectivity

### "Invalid API Key" Error
- Confirm the API key matches your backend configuration
- Check for extra spaces or characters

### Video Stream Not Loading
- Verify the video stream URL is accessible
- Check that your robot's camera is active
- Try accessing the stream URL in Safari

## Next Steps

Now that you're set up:

- 📖 Read the full [README](README.md) for detailed features
- 🛠 Customize controls in `Config.swift`
- 🎨 Modify the UI in `ContentView.swift`
- 🤖 Add new robot commands in `RobotController.swift`

## Need Help?

- 📋 Check [existing issues](https://github.com/yourusername/ev3iPhoneController/issues)
- 💬 Open a new issue with the `question` label
- 📧 Contact the maintainer

## Testing Without Hardware

If you don't have an EV3 robot yet, you can:

1. Create a mock backend that returns success responses
2. Test the UI and controls in the simulator
3. Use Postman to simulate backend responses

Example mock backend (Node.js):

```javascript
const express = require('express');
const app = express();

app.use(express.json());

app.post('/controlRobot', (req, res) => {
  console.log('Received command:', req.body);
  res.json({ success: true, message: 'Command received' });
});

app.listen(3000, () => console.log('Mock server running on port 3000'));
```

Happy robot controlling! 🤖🎮
