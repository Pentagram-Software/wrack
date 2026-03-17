# 🤖 Mindstorms Cloud Controller

A Google Cloud Function that provides remote control capabilities for LEGO Mindstorms EV3 robots over TCP/IP connection. This project enables controlling your EV3 robot from anywhere via HTTP API, bridging web applications to physical robotics.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Node.js Version](https://img.shields.io/badge/node-%3E%3D20-brightgreen.svg)](https://nodejs.org/)
[![Google Cloud](https://img.shields.io/badge/Google%20Cloud-Functions-4285F4.svg)](https://cloud.google.com/functions)

---

## 📋 Table of Contents

- [Architecture](#architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [API Documentation](#api-documentation)
- [Available Commands](#available-commands)
- [Usage Examples](#usage-examples)
- [Project Structure](#project-structure)
- [Development](#development)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## 🏗️ Architecture

```
┌─────────────────┐         HTTPS/POST          ┌──────────────────────┐
│                 │    (JSON Command)            │                      │
│  Client App     │ ──────────────────────────>  │  Google Cloud        │
│  (Web/Mobile)   │                              │  Function            │
│                 │ <────────────────────────────│  (Node.js 20)        │
└─────────────────┘    JSON Response             └──────────────────────┘
                                                           │
                                                           │ TCP/JSON
                                                           │ Port 27700
                                                           ▼
                                                  ┌──────────────────────┐
                                                  │  EV3 Robot           │
                                                  │  Python Server       │
                                                  │  (Pybricks)          │
                                                  └──────────────────────┘
```

### Components

1. **Cloud Function (index.js)**: HTTP endpoint that validates requests, authenticates via API key, and forwards commands to the EV3 robot
2. **Robot Server (robot-server.py)**: Python TCP server running on EV3 that controls motors, sensors, and speakers
3. **Authentication Layer (auth.js)**: API key validation for securing the endpoint
4. **Client Examples**: Test utilities and example clients in JavaScript and Python

---

## ✨ Features

### Robot Control
- **Vehicle Movement**: Forward, backward, left, right with configurable speed and duration
- **Turret Control**: Independent turret rotation (left/right) with stop control
- **Joystick Mode**: Real-time joystick-style control with dual-stick support
- **Emergency Stop**: Immediate stop of all motors or turret-only stop

### Audio & Feedback
- **Text-to-Speech**: Make the robot speak any text (up to 500 characters)
- **Beep**: Custom frequency and duration beep sounds

### Monitoring
- **Status Query**: Get comprehensive robot status including:
  - Battery level, voltage, current draw
  - Motor positions, speeds, and stall detection
  - Sensor readings (ultrasonic, gyro, camera)
  - Active connections and command history
  - Device ports and availability
  - System information (CPU, network, OS)

### Safety Features
- Speed limits (0-2000) enforced
- Duration limits (max 10 seconds per command)
- Connection timeout (5 seconds)
- API key authentication
- CORS enabled for web applications

---

## 📦 Prerequisites

### Cloud Side
- **Google Cloud Platform** account with billing enabled
- **gcloud CLI** installed and configured
- **Node.js 20** or higher
- **npm** package manager

### Robot Side
- **LEGO Mindstorms EV3** robot
- **ev3dev** operating system installed on EV3
- **Pybricks** library for EV3 Python
- **Network connectivity** (WiFi or Ethernet) for the EV3
- **Static IP** or accessible hostname for the EV3

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/mindstorms-cloud-controller.git
cd mindstorms-cloud-controller
```

### 2. Install Dependencies

```bash
npm install
```

### 3. Deploy Robot Server to EV3

Copy `robot-server.py` to your EV3 robot and ensure it runs on startup:

```bash
# On your EV3 (via SSH)
python3 robot-server.py
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file or set environment variables:

```bash
ROBOT_HOST=<your-ev3-ip-address>    # e.g., 192.168.1.100
ROBOT_PORT=27700                     # Default EV3 server port
API_KEY=<your-secure-api-key>       # Generate a strong random key
```

### Hardware Configuration

Update `robot-server.py` if your motor/sensor ports differ:

```python
self.left_motor = Motor(Port.A)      # Left drive motor
self.right_motor = Motor(Port.D)     # Right drive motor
self.turret_motor = Motor(Port.C)    # Turret motor
self.ultrasonic_sensor = UltrasonicSensor(Port.S2)
self.gyro_sensor = GyroSensor(Port.S3)
```

---

## 🌐 Deployment

### Deploy to Google Cloud Functions

```bash
# Using npm script (recommended)
npm run deploy

# Or manually with gcloud
gcloud functions deploy controlRobot \
  --runtime nodejs20 \
  --trigger-http \
  --allow-unauthenticated \
  --region europe-central2 \
  --set-env-vars ROBOT_HOST=192.168.1.100,ROBOT_PORT=27700,API_KEY=your-api-key
```

### Verify Deployment

```bash
gcloud functions describe controlRobot --region europe-central2
```

Your function will be available at:
```
https://<region>-<project-id>.cloudfunctions.net/controlRobot
```

---

## 📖 API Documentation

### Authentication

All requests require an API key in the header:

```
X-API-Key: your-api-key
```

### Request Format

```http
POST /controlRobot
Content-Type: application/json
X-API-Key: your-api-key

{
  "command": "command_name",
  "params": {
    "param1": "value1",
    "param2": "value2"
  }
}
```

### Response Format

#### Success Response
```json
{
  "success": true,
  "command": "command_name",
  "result": {
    "status": "success",
    "action": "command_name",
    ...additional data...
  },
  "timestamp": "2025-10-05T10:00:00.000Z"
}
```

#### Error Response
```json
{
  "success": false,
  "error": "Error message",
  "timestamp": "2025-10-05T10:00:00.000Z"
}
```

---

## 🎮 Available Commands

### Vehicle Movement

| Command | Parameters | Description |
|---------|------------|-------------|
| `forward` | `speed` (default: 500)<br>`duration` (default: 0) | Move robot forward |
| `backward` | `speed` (default: 500)<br>`duration` (default: 0) | Move robot backward |
| `left` | `speed` (default: 300)<br>`duration` (default: 0) | Turn robot left |
| `right` | `speed` (default: 300)<br>`duration` (default: 0) | Turn robot right |
| `stop` | None | Stop all motors immediately |

### Turret Control

| Command | Parameters | Description |
|---------|------------|-------------|
| `turret_left` | `speed` (default: 200)<br>`duration` (default: 0) | Rotate turret left |
| `turret_right` | `speed` (default: 200)<br>`duration` (default: 0) | Rotate turret right |
| `stop_turret` | None | Stop turret motor only |

### Audio Commands

| Command | Parameters | Description |
|---------|------------|-------------|
| `speak` | `text` (required, max 500 chars) | Text-to-speech output |
| `beep` | `frequency` (optional)<br>`duration` (optional) | Play beep sound |

### System Commands

| Command | Parameters | Description |
|---------|------------|-------------|
| `get_status` | None | Get full robot status |
| `battery` | None | Get battery information |
| `get_help` | None | Get available commands |
| `joystick_control` | `l_left`, `l_forward`<br>`r_left`, `r_forward` | Joystick control mode |

**Note**: `duration: 0` means continuous movement until a stop command is sent.

---

## 💡 Usage Examples

### JavaScript/Node.js

```javascript
const axios = require('axios');

const API_URL = 'https://europe-central2-yourproject.cloudfunctions.net/controlRobot';
const API_KEY = 'your-api-key';

async function moveForward() {
  const response = await axios.post(API_URL, {
    command: 'forward',
    params: { speed: 500, duration: 2 }
  }, {
    headers: { 'X-API-Key': API_KEY }
  });
  console.log(response.data);
}

async function speak() {
  const response = await axios.post(API_URL, {
    command: 'speak',
    params: { text: 'Hello from the cloud!' }
  }, {
    headers: { 'X-API-Key': API_KEY }
  });
  console.log(response.data);
}

async function getStatus() {
  const response = await axios.post(API_URL, {
    command: 'get_status'
  }, {
    headers: { 'X-API-Key': API_KEY }
  });
  console.log('Battery:', response.data.result.device_info.battery.percentage + '%');
  console.log('Motors:', response.data.result.device_info.motors);
}
```

### Python

```python
import requests

API_URL = 'https://europe-central2-yourproject.cloudfunctions.net/controlRobot'
API_KEY = 'your-api-key'

def send_command(command, params=None):
    response = requests.post(
        API_URL,
        json={'command': command, 'params': params or {}},
        headers={'X-API-Key': API_KEY}
    )
    return response.json()

# Move forward
result = send_command('forward', {'speed': 500, 'duration': 2})
print(result)

# Make robot speak
result = send_command('speak', {'text': 'Hello World'})
print(result)

# Get battery status
result = send_command('battery')
print(f"Battery: {result['result']['battery']['percentage']}%")
```

### cURL

```bash
# Move forward
curl -X POST https://europe-central2-yourproject.cloudfunctions.net/controlRobot \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"command": "forward", "params": {"speed": 500, "duration": 2}}'

# Text-to-speech
curl -X POST https://europe-central2-yourproject.cloudfunctions.net/controlRobot \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"command": "speak", "params": {"text": "Hello from the cloud"}}'

# Get robot status
curl -X POST https://europe-central2-yourproject.cloudfunctions.net/controlRobot \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"command": "get_status"}'
```

---

## 📁 Project Structure

```
mindstorms-cloud-controller/
├── index.js                 # Main Cloud Function handler
├── auth.js                  # API key authentication
├── robot-server.py          # EV3 Python server (deploy to robot)
├── test-client.js           # Test client for development
├── example_client.py        # Python example client
├── package.json             # Node.js dependencies
├── cloudbuild.yaml          # Cloud Build configuration
├── deploy.yaml              # Deployment configuration
├── Dockerfile               # Container configuration
├── .gitignore               # Git ignore patterns
├── .gcloudignore            # GCloud ignore patterns
├── PROJECT_STATUS.md        # Detailed project status and roadmap
├── CLAUDE.md                # AI development context
└── README.md                # This file
```

---

## 🛠️ Development

### Local Testing

Run the Cloud Function locally:

```bash
npm start
```

Test against the local function:

```bash
# Update test-client.js with local URL
node test-client.js
```

### Running Tests

```bash
npm test
```

### Linting

```bash
npm run lint
```

---

## 🔒 Security

### Best Practices

1. **Change the default API key** in deployment to a strong random value:
   ```bash
   # Generate a secure API key
   openssl rand -hex 32
   ```

2. **Use environment variables** for sensitive data - never commit API keys to git

3. **Restrict CORS** if you know your client domains:
   ```javascript
   // In index.js
   const corsHandler = cors({
     origin: 'https://yourdomain.com',  // Replace with your domain
     methods: ['POST', 'OPTIONS']
   });
   ```

4. **Enable VPC** for production to restrict EV3 access to Cloud Functions only

5. **Monitor logs** for suspicious activity:
   ```bash
   gcloud functions logs read controlRobot --region europe-central2
   ```

### Network Security

- The EV3 must be reachable from Cloud Functions (open port 27700)
- Consider using Cloud VPN for production deployments
- Use firewall rules to restrict EV3 access

---

## 🐛 Troubleshooting

### Common Issues

**Connection Timeout**
- Ensure EV3 robot server is running
- Verify `ROBOT_HOST` and `ROBOT_PORT` are correct
- Check network connectivity between Cloud Function and EV3
- Verify firewall rules allow TCP on port 27700

**Authentication Failed**
- Check `X-API-Key` header is present
- Verify API key matches deployment configuration
- Ensure no extra whitespace in the key

**Commands Not Executing**
- Check Cloud Function logs for errors
- Verify EV3 motors/sensors are connected to correct ports
- Ensure sufficient battery level on EV3

### Viewing Logs

```bash
# Cloud Function logs
gcloud functions logs read controlRobot --region europe-central2 --limit 50

# Real-time logs
gcloud functions logs read controlRobot --region europe-central2 --tail
```

### Debug Mode

Enable verbose logging in `index.js` for detailed debugging (already enabled in current version).

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🙏 Acknowledgments

- Built with [Google Cloud Functions](https://cloud.google.com/functions)
- Robot control powered by [Pybricks](https://pybricks.com/)
- LEGO Mindstorms EV3 platform

---

## 📞 Support

For issues, questions, or contributions, please open an issue on GitHub.

**Project maintained by**: Your Name
**Repository**: https://github.com/yourusername/mindstorms-cloud-controller
