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
- **index.js**: Robot control Cloud Function (`controlRobot`) - processes HTTP requests, validates commands, manages TCP connection to robot, emits `api_request` telemetry events. Also requires `telemetry.js` and `ingress.js` so all three functions are registered.
- **api-telemetry.js**: Fire-and-forget telemetry helper used by `controlRobot`. Builds `api_request` events and inserts them to BigQuery via `setImmediate` (non-blocking). Errors are swallowed so they cannot affect command execution.
- **telemetry.js**: Telemetry ingestion Cloud Function (`telemetryIngestion`) - accepts batched events, validates schema, batch-inserts into BigQuery `wrack_telemetry.events`. Legacy single-purpose endpoint, shared-key auth — `ingress.js` supersedes it for new senders but it stays live during migration.
- **ingress.js**: Unified ingress Cloud Function (`unifiedIngress`, PEN-227) - the target endpoint for EV3/Pi telemetry going forward. Per-device auth (`X-Device-Id`/`X-Device-Token` against the `device-tokens` Secret Manager secret, not the shared `API_KEY`). Routes each event by its optional `type` field: `event` (default) → `bigquery-client.js insertEvents()`; `health` → a direct synchronous POST to `HEALTH_LEG_FUNCTION_URL` (`healthLegPush`, PEN-228), authenticated with a Google-signed OIDC identity token (`google-auth-library`, cached at module scope with single-flight dedup so a concurrent fan-out of pushes doesn't each hit the metadata server) attached as `Authorization: Bearer <token>`. Fails open (logged and dropped, never surfaced as a failure) when the URL is unset, the token can't be acquired, or the call errors. Reuses `telemetry.js`'s `validateEvent` for envelope validation.
- **health-leg.js**: Health-leg push Cloud Function (`healthLegPush`, PEN-228) - the receiving end of `unifiedIngress`'s `type=health` leg. Receives one health record per POST, maps it to OTLP metrics (numeric payload fields, via `otlp-mapper.js`) and a structured log record (full payload), and pushes both to Grafana Cloud's hosted OTLP gateway using `@opentelemetry/exporter-metrics-otlp-http` + `-logs-otlp-http`, authenticated with Basic Auth (Grafana instance ID + Access Policy token from `grafana-credentials.js`). Deployed `--no-allow-unauthenticated` — its only caller is `unifiedIngress`, so GCP IAM (Cloud Run invoker role) gates access instead of an app-level check. Fails open on any push failure (logged, dropped, never retried).
- **otlp-mapper.js**: Pure field-mapping logic used by `health-leg.js` — turns a validated health event into OTLP gauge metric points (one per numeric/boolean payload field, named `wrack.<event_type>.<field>`) and a single structured log record (full payload as body, severity elevated for `error` events and problem-state `device_status` events). No OTLP client/network code, so it's independently unit-testable.
- **grafana-credentials.js**: Loads `{otlp_endpoint, instance_id, token}` from the `grafana-cloud-push-credentials` Secret Manager secret (PEN-189, provisioned by `cloud/monitoring/setup-grafana-secret.sh`) for `health-leg.js`. TTL-cached across warm invocations, mirroring `ingress.js`'s device-tokens cache.
- **setup-device-tokens.sh**: Generates/rotates per-device tokens and stores them as the `device-tokens` Secret Manager secret `ingress.js` reads at cold start. Mirrors `cloud/monitoring/setup-grafana-secret.sh`'s structure.
- **bigquery-client.js**: Reusable BigQuery wrapper — lazy singleton init, `insertEvent`, `insertEvents` batch, exponential-backoff retry for 429/5xx/UNAVAILABLE errors, `PartialFailureError` handling. Opt-in/fail-safe: omitting `BIGQUERY_PROJECT_ID` silently disables all inserts.
- **index.test.js**: Jest unit tests for `controlRobot` (authentication, command validation, dispatching, error handling).
- **telemetry.test.js**: Jest unit tests for `telemetryIngestion` (32 tests covering validation, BigQuery inserts, partial failures, auth).
- **ingress.test.js**: Jest unit tests for `unifiedIngress` (per-device auth, type-field routing, health-leg fail-open behaviour, identity-token acquisition/caching/concurrency).
- **health-leg.test.js**: Jest unit tests for `healthLegPush` (OTLP exporter wiring, fail-open on downstream push failure, 401/403 left to GCP IAM, request validation).
- **otlp-mapper.test.js**: Jest unit tests for the health-event → OTLP metrics/logs field mapping.
- **grafana-credentials.test.js**: Jest unit tests for the Grafana credentials Secret Manager loader (TTL cache, shape validation).
- **bigquery-client.test.js**: Jest unit tests for the BigQuery client wrapper (60 tests covering isEnabled, _formatRow, _isRetryableError, insertEvent, insertEvents, retry behaviour, client initialisation).
- **auth.js**: API authentication logic using X-API-Key header (shared static key, used by `controlRobot` and `telemetryIngestion` only — `ingress.js` uses its own per-device token check instead).
- **robot-server.py**: Python server running on EV3 robot (separate device) - receives TCP commands and controls motors.
- **test-client.js**: Test utilities and client examples for development.

---

## API Specification

### controlRobot endpoint
**URL:** `https://europe-central2-[PROJECT-ID].cloudfunctions.net/controlRobot`
**Method:** POST
**Region:** europe-central2
**Authentication:** API Key via `X-API-Key` header

### telemetryIngestion endpoint
**URL:** `https://europe-central2-[PROJECT-ID].cloudfunctions.net/telemetryIngestion`
**Method:** POST
**Region:** europe-central2
**Authentication:** API Key via `X-API-Key` header

**Request:**
```json
{
  "events": [
    {
      "event_id": "uuid-v4",
      "event_type": "battery_status",
      "source": "ev3",
      "timestamp": "2024-01-15T10:00:00.000Z",
      "payload": { "voltage_mv": 7200, "percentage": 85 },
      "device_id": "ev3-001",
      "session_id": "sess-abc",
      "version": "1.0.0",
      "tags": ["production"],
      "user_id": "user-1",
      "correlation_id": "corr-1"
    }
  ]
}
```

**Required event fields:** `event_id`, `event_type`, `source`, `timestamp` (ISO 8601), `payload` (object).
**Optional event fields:** `device_id`, `session_id`, `version`, `tags` (string array), `user_id`, `correlation_id`.

**Response (all inserted — HTTP 200):**
```json
{ "success": true, "inserted": 5, "failed": 0 }
```

**Response (partial — HTTP 207):**
```json
{
  "success": false,
  "inserted": 3,
  "failed": 2,
  "errors": [
    { "index": 1, "event_id": "uuid-bad", "errors": ["event_type is required"] }
  ]
}
```

**Environment variables required:**
```bash
API_KEY=your-secure-api-key-here
BIGQUERY_PROJECT_ID=wrack-control   # required to enable telemetry; omitting silently disables bigquery-client.js
BIGQUERY_DATASET=wrack_telemetry    # optional, defaults to "wrack_telemetry"
BIGQUERY_TABLE=events               # optional, defaults to "events"
```

### unifiedIngress endpoint (PEN-227)
**URL:** `https://europe-central2-[PROJECT-ID].cloudfunctions.net/unifiedIngress`
**Method:** POST
**Region:** europe-central2
**Authentication:** per-device — `X-Device-Id` + `X-Device-Token` headers, checked against the `device-tokens` Secret Manager secret (not `X-API-Key`)

**Request:** identical `{"events": [...]}` batch shape as `telemetryIngestion`, plus an optional `type` field per event (`"health"` or `"event"`; defaults to `"event"` when absent).

**Response shapes:** identical 200/207/400 shapes as `telemetryIngestion` — health-tagged records always count toward `inserted` regardless of downstream push outcome (fail-open).

**Environment variables required:**
```bash
GCP_PROJECT_ID=wrack-control            # project the device-tokens secret lives in
DEVICE_TOKENS_SECRET=device-tokens      # optional, defaults to "device-tokens"
BIGQUERY_PROJECT_ID=wrack-control       # analytics leg, same as telemetryIngestion
BIGQUERY_DATASET=wrack_telemetry        # optional
HEALTH_LEG_FUNCTION_URL=                # healthLegPush's URL; unset means health records fail open (logged, dropped)
```

Provision device tokens with `bash setup-device-tokens.sh --device-id ev3-001 --device-id rpi-camera-01` (see the script header for full usage).

### healthLegPush endpoint (PEN-228)
**URL:** `https://europe-central2-[PROJECT-ID].cloudfunctions.net/healthLegPush` (what `unifiedIngress`'s `HEALTH_LEG_FUNCTION_URL` should point at)
**Method:** POST
**Region:** europe-central2
**Authentication:** GCP IAM only (deployed `--no-allow-unauthenticated`) — no app-level check. `unifiedIngress`'s runtime service account is granted `roles/run.invoker` on it; `unifiedIngress` attaches a Google-signed OIDC identity token as `Authorization: Bearer <token>`. A request without a valid token is rejected by the platform before this function's code runs.

**Request:** a single telemetry event object (not a batch) — `unifiedIngress`'s `pushHealthRecord()` calls this once per health record.

**Response:** `{"success": true}` (200) on a successful push; `{"error": "..."}` (400) for a malformed body; `{"success": false, "error": "push failed"}` (502) only when Grafana credentials themselves can't be loaded — any downstream OTLP push failure is logged and swallowed internally (fails open, still 200).

**Environment variables required:**
```bash
GCP_PROJECT_ID=wrack-control                          # project the credentials secret lives in
GRAFANA_CREDENTIALS_SECRET=grafana-cloud-push-credentials  # optional, defaults to this name
```

Provision Grafana credentials with `cloud/monitoring/setup-grafana-secret.sh` (PEN-189) before deploying this function.

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
# Local dev servers
npm start                   # Start controlRobot on port 8080
npm run start:telemetry     # Start telemetryIngestion on port 8080
npm run start:ingress       # Start unifiedIngress on port 8080
npm run start:health-leg    # Start healthLegPush on port 8080 (no local IAM check — POST a single event directly)

# Deployment
npm run deploy              # Deploy controlRobot to GCP europe-central2
npm run deploy:telemetry    # Deploy telemetryIngestion to GCP europe-central2
npm run deploy:ingress      # Deploy unifiedIngress to GCP europe-central2
npm run deploy:health-leg   # Deploy healthLegPush to GCP europe-central2 (--no-allow-unauthenticated)
gcloud builds submit --config cloudbuild.yaml  # Deploy all four via Cloud Build (healthLegPush before unifiedIngress, so its URL/IAM grants are ready first)

# Device tokens (unifiedIngress only)
bash setup-device-tokens.sh --device-id ev3-001 --device-id rpi-camera-01

# Testing
npm run test-robot         # Test all robot commands (requires live robot)
npm test                   # Run all unit tests (Jest)
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
