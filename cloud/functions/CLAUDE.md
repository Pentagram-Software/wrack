# 🤖 Mindstorms Cloud Controller - Claude AI Context

## Project Overview
A Google Cloud Function that provides remote control capabilities for LEGO Mindstorms EV3 robots over IP connection. The system acts as a bridge between client applications and an EV3 robot, handling authentication, command validation, and TCP communication.

**Current Status:** Active Development | Version 1.0.0

---

## Architecture

### System Flow
```
Client App → Cloud Function (HTTP/POST) → EV3 Robot (TCP/JSON)
```

The Cloud Function receives HTTP POST requests with commands, validates authentication, enforces safety limits, forwards commands to the EV3 robot over TCP, and returns responses to the client.

### Key Components
- **index.js**: Main Cloud Function handler - processes HTTP requests, validates commands, manages TCP connection to robot
- **auth.js**: API authentication logic using X-API-Key header
- **robot-server.py**: Python server running on EV3 robot (separate device) - receives TCP commands and controls motors
- **test-client.js**: Test utilities and client examples for development

---

## API Specification

### Endpoint
**URL:** `https://europe-central2-[PROJECT-ID].cloudfunctions.net/controlRobot`
**Method:** POST
**Region:** europe-central2
**Authentication:** API Key via `X-API-Key` header

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

## Available Commands

### Vehicle Movement
- `forward` - Move robot forward (speed: 500, duration: 0)
- `backward` - Move robot backward (speed: 500, duration: 0)
- `left` - Turn robot left (speed: 300, duration: 0)
- `right` - Turn robot right (speed: 300, duration: 0)

### Turret Control
- `turret_left` - Turn turret left (speed: 200, duration: 0)
- `turret_right` - Turn turret right (speed: 200, duration: 0)
- `stop_turret` - Stop turret only (no parameters)

### System Commands
- `stop` - Stop all motors
- `get_status` - Get robot status
- `get_help` - Get help information
- `joystick_control` - Joystick input (l_left, l_forward, r_left, r_forward)
- `speak` - Text-to-speech (text: string, max 500 chars)
- `battery` - Get battery status (no parameters)
- `beep` - Play beep sound (frequency: optional, duration: optional)

**Note:** Duration of 0 means continuous movement until stop command is sent.

---

## Critical Configuration

### Environment Variables
```bash
ROBOT_HOST=178.183.200.201    # EV3 robot IP address
ROBOT_PORT=27700              # EV3 robot TCP port
API_KEY=abc123def456ghi789jkl012mno345pq  # Authentication key
```

### Safety Constraints
- Speed Range: 0-2000 (enforced)
- Duration Limit: 10 seconds max (enforced)
- Connection Timeout: 5 seconds
- TCP Protocol: JSON messages with newline terminator

### Hardware Setup
- EV3 Robot IP: 178.183.200.201:27700
- Turret Motor: Port A
- Drive Motors: Standard ports

---

## Development Commands

```bash
# Deployment
npm run deploy              # Deploy to Google Cloud Functions
gcloud functions deploy controlRobot  # Direct gcloud deploy
gcloud builds submit --config cloudbuild.yaml  # Cloud Build deploy

# Testing
npm run test-robot         # Test all robot commands
npm test                   # Run unit tests
npm run lint              # Code linting
```

---

## Implementation Notes for AI Assistance

### When Making Changes
1. **Command validation** happens in index.js - any new commands need validation logic
2. **Safety limits** must be enforced for speed (0-2000) and duration (max 10s)
3. **TCP communication** uses newline-terminated JSON messages
4. **CORS** is enabled for all origins - maintain for web client compatibility
5. **Error handling** should return descriptive messages in response.error field

### Common Modification Scenarios

**Adding a new command:**
1. Define command in supported commands list in index.js
2. Add parameter validation with defaults in validateCommand()
3. Add case in switch statement to set action and extraParams
4. Update robot-server.py handle_command() to handle the action
5. Implement handler method in robot-server.py
6. Update help information in _get_help()
7. Add test cases in test-client.js
8. Update documentation

**Modifying safety limits:**
- Update validation logic in index.js
- Ensure limits match robot hardware capabilities
- Document changes in PROJECT_STATUS.md

**Changing authentication:**
- Modify auth.js for new auth scheme
- Update CORS configuration if needed
- Update client examples

**Text-to-Speech Implementation (speak command):**
- Cloud Function validates text parameter (required, max 500 chars)
- Text is passed to robot via extraParams object
- Robot uses ev3.speaker.say() from pybricks library
- Simulation mode prints text instead of speaking
- Command returns success with echoed text

**Battery Status (battery command):**
- Cloud Function sends action: "battery" to EV3
- EV3 responds with voltage_mv, voltage_v, current_ma, percentage, battery_type
- No parameters required
- Returns comprehensive battery information

**Beep Sound (beep command):**
- Cloud Function sends action: "beep" with optional frequency and duration
- If frequency/duration not provided, EV3 uses defaults
- Both parameters are optional and forwarded as-is to EV3
- EV3 handles the actual beep generation

### Testing Considerations
- Robot must be running on 178.183.200.201:27700 for live tests
- Use test-client.js for API testing without deploying
- Commands with duration=0 require manual stop command
- Connection timeout is 5 seconds - handle gracefully

---

## Current Priorities & Roadmap

### Immediate Improvements
- Camera control commands (if camera attached)
- Sensor reading endpoints (distance, color, touch)
- Movement queuing system for complex maneuvers
- WebSocket support for real-time control

### API Enhancements
- Rate limiting to prevent command spam
- Better command validation with error messages
- Batch command execution for synchronized movements
- Movement recording/playback functionality

### Infrastructure
- Cloud Monitoring for function performance
- Structured logging
- Alerting for robot disconnection
- Health check endpoint for connectivity

### Security
- JWT tokens instead of static API key
- Request signing for enhanced security
- Connection pooling for performance
- Automatic retry logic for failed commands

---

## Important Context for Code Modifications

### File Relationships
- index.js calls auth.js for authentication
- index.js communicates with robot-server.py via TCP
- test-client.js mimics real client behavior for testing
- Environment variables are required for all deployments

### Hardware Constraints
- EV3 motors have speed range 0-2000
- Long-running commands drain battery quickly
- Network latency affects command responsiveness
- Turret motor on Port A has specific calibration needs

### API Usage Patterns
- Commands are non-blocking by default
- duration=0 means continuous until stop
- stop_turret is independent from stop (all motors)
- Always check response.success before assuming execution

---

*This document is maintained as context for Claude AI to assist with development and modifications.*
