# 🤖 Mindstorms Cloud Controller - Project Status

## 📊 Project Overview
**Status:** ✅ Active Development  
**Version:** 1.0.0  
**Last Updated:** August 24, 2025

A Google Cloud Function that provides remote control capabilities for LEGO Mindstorms EV3 robots over IP connection.

---

## 🏗️ Architecture

### System Components
```
┌─────────────┐    HTTP/POST    ┌──────────────────┐    TCP/JSON    ┌─────────────┐
│             │   ──────────>   │                  │  ────────────> │             │
│ Client App  │                 │ Google Cloud     │                │ EV3 Robot   │
│             │   <──────────   │ Function         │  <──────────── │             │
└─────────────┘    JSON Resp    └──────────────────┘    JSON Resp   └─────────────┘
```

### Core Files
| File | Purpose | Status |
|------|---------|---------|
| `index.js` | Main Cloud Function handler | ✅ Active |
| `auth.js` | API authentication logic | ✅ Active |
| `robot-server.py` | EV3 robot server (separate device) | ✅ Active |
| `test-client.js` | Test utilities and client examples | ✅ Active |

---

## 🔌 API Integration

### Endpoint
**URL:** `https://europe-central2-[PROJECT-ID].cloudfunctions.net/controlRobot`  
**Method:** POST  
**Region:** europe-central2

### Authentication
**Type:** API Key  
**Header:** `X-API-Key: abc123def456ghi789jkl012mno345pq`  
**CORS:** Enabled for all origins with POST/OPTIONS methods

### Request Format
```json
{
  "command": "command_name",
  "params": {
    "speed": 200,
    "duration": 1.0
  }
}
```

### Response Format
```json
{
  "success": true,
  "command": "turret_left",
  "result": {
    "success": true,
    "action": "turret_left",
    "speed": 200,
    "duration": 1
  },
  "timestamp": "2025-08-24T12:00:00.000Z"
}
```

---

## 🎮 Supported Commands

### Vehicle Movement
| Command | Description | Parameters |
|---------|-------------|------------|
| `forward` | Move robot forward | `speed` (default: 500), `duration` (default: 0) |
| `backward` | Move robot backward | `speed` (default: 500), `duration` (default: 0) |
| `left` | Turn robot left | `speed` (default: 300), `duration` (default: 0) |
| `right` | Turn robot right | `speed` (default: 300), `duration` (default: 0) |

### Turret Control
| Command | Description | Parameters |
|---------|-------------|------------|
| `turret_left` | Turn turret left | `speed` (default: 200), `duration` (default: 0) |
| `turret_right` | Turn turret right | `speed` (default: 200), `duration` (default: 0) |
| `stop_turret` | **🆕 Stop turret only** | None |

### System Commands
| Command | Description | Parameters |
|---------|-------------|------------|
| `stop` | Stop all motors | None |
| `get_status` | Get robot status | None |
| `get_help` | Get help information | None |
| `joystick_control` | Joystick input | `l_left`, `l_forward`, `r_left`, `r_forward` |
| `speak` | **🆕 Text-to-speech** | `text` (string, max 500 chars) |
| `battery` | **🆕 Get battery status** | None |
| `beep` | **🆕 Play beep sound** | `frequency` (optional), `duration` (optional) |

---

## 🔧 Critical Configuration

### Environment Variables
```bash
ROBOT_HOST=178.183.200.201    # EV3 robot IP address
ROBOT_PORT=27700              # EV3 robot TCP port  
API_KEY=abc123def456ghi789jkl012mno345pq  # Authentication key
```

### Safety Limits
- **Speed Range:** 0-2000 (enforced)
- **Duration Limit:** 10 seconds max (enforced)
- **Connection Timeout:** 5 seconds
- **TCP Protocol:** JSON messages with newline terminator

### Hardware Setup
- **EV3 Robot IP:** 178.183.200.201:27700
- **Turret Motor:** Connected to Port A
- **Drive Motors:** Connected to standard ports

---

## 🚀 Deployment

### Quick Deploy Commands
```bash
# Method 1: Using npm script (recommended)
npm run deploy

# Method 2: Using gcloud directly  
gcloud functions deploy controlRobot

# Method 3: Using Cloud Build
gcloud builds submit --config cloudbuild.yaml
```

### Testing
```bash
npm run test-robot    # Test all commands
npm test             # Run unit tests
npm run lint         # Code linting
```

---

## 🔮 Next Steps & Roadmap

### Immediate Improvements
- [ ] **Add camera control commands** (if camera is attached)
- [ ] **Implement sensor reading endpoints** (distance, color, touch)
- [ ] **Add movement queuing system** for complex maneuvers
- [ ] **Create WebSocket support** for real-time control

### API Enhancements
- [ ] **Rate limiting implementation** to prevent command spam
- [ ] **Command validation** with better error messages
- [ ] **Batch command execution** for synchronized movements
- [ ] **Movement recording/playback** functionality

### Infrastructure & Monitoring
- [ ] **Add Cloud Monitoring** for function performance
- [ ] **Implement proper logging** with structured logs
- [ ] **Set up alerting** for robot disconnection
- [ ] **Add health check endpoint** for robot connectivity

### Client Integration
- [ ] **Create React/Flutter UI components** for easy integration
- [ ] **Build JavaScript SDK** for web applications
- [ ] **Add Python client library** for automation scripts
- [ ] **WebRTC video streaming** for remote viewing

### Security & Reliability
- [ ] **Implement JWT tokens** instead of static API key
- [ ] **Add request signing** for enhanced security
- [ ] **Connection pooling** for better performance
- [ ] **Automatic retry logic** for failed commands

---

## 📝 Integration Notes

### For App Developers
1. **Always include** `X-API-Key` header in requests
2. **Handle timeouts** gracefully (5-second limit)
3. **Check response.success** before assuming command executed
4. **Use duration=0** for continuous movement until stop command
5. **Commands are non-blocking** - send stop_turret on button release

### For Robot Operators
1. **Ensure robot server is running** on 178.183.200.201:27700
2. **Monitor robot battery level** - low battery affects motor performance  
3. **Check network connectivity** between GCP and robot regularly
4. **Turret motor calibration** may be needed for accurate positioning

---

## 🎯 Recent Changes

### Latest Updates (October 2025)
- ✅ **Added `speak` command** for text-to-speech functionality
- ✅ **Added `battery` command** to query battery status
- ✅ **Added `beep` command** with optional frequency and duration
- ✅ **Added `stop_turret` command** for independent turret stopping
- ✅ **Improved TCP data handling** to process multiple packets correctly
- ✅ **Enhanced response parsing** to skip non-JSON messages
- ✅ **Enhanced CORS configuration** with OPTIONS method support
- ✅ **Updated API key handling** in headers
- ✅ **Improved error handling** with detailed responses

---

*This document is automatically generated and maintained as part of the project documentation.*