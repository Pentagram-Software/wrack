# BigQuery Data Tracking Requirements

## Overview

This document defines the requirements for implementing a cloud-based data tracking system using Google BigQuery. The system will collect telemetry and events from the Wrack robot system components (EV3, Raspberry Pi) for analytics, monitoring, and future machine learning applications.

## Problem Statement

Currently, all events and telemetry in the Wrack system are:
- **Local and ephemeral**: Events are handled in-memory via `EventHandler` on the EV3
- **Not persisted**: No historical data is stored for analysis
- **Not centralized**: Each component logs independently with no aggregation
- **Not queryable**: No way to analyze patterns, debug issues post-hoc, or train ML models

The README mentions "vision data → BigQuery" but this is not implemented.

## Goals

1. **Centralized telemetry**: Collect significant events from all system components into BigQuery
2. **Historical analysis**: Enable querying of historical data for debugging and analytics
3. **Real-time monitoring**: Support near real-time dashboards for system health
4. **ML readiness**: Structure data to support future machine learning pipelines
5. **Extensibility**: Design for easy addition of new event types and data sources

## Non-Goals

- Real-time stream processing (Pub/Sub → Dataflow) - future enhancement
- Custom visualization dashboards - use Looker Studio / Data Studio initially
- On-device ML inference - this is for data collection only
- Complete event replay system - focus on analytics, not event sourcing

## Data Sources

### 1. EV3 Robot Controller (Primary - Phase 1)

| Event Category | Events | Priority |
|---------------|--------|----------|
| **Power/Battery** | Battery voltage, current, percentage, critical warnings | P0 |
| **Movement Controls** | Commands received (forward, backward, left, right, stop), joystick inputs | P0 |
| **Device Status** | Device connected/disconnected, motor stall detection | P0 |
| **Critical Alerts** | Errors, exceptions, watchdog triggers | P0 |
| **Position/Sensors** | Gyro readings, ultrasonic distance, terrain scan data | P1 |
| **Wake Word** | "Hey Wrack" detections | P2 |
| **Camera** | Pixy camera block detections | P2 |

### 2. Raspberry Pi Edge (Phase 2)

| Event Category | Events | Priority |
|---------------|--------|----------|
| **Vision/ML** | Object detections, classifications, confidence scores | P1 |
| **Video Stream** | Stream health, frame drops, encoding stats | P2 |
| **System Health** | CPU, memory, temperature | P2 |

### 3. Cloud Functions (Phase 1)

| Event Category | Events | Priority |
|---------------|--------|----------|
| **API Requests** | Command requests, latency, errors | P0 |
| **Connection Status** | EV3 connection success/failure, timeouts | P0 |

### 4. Web/iOS Clients (Phase 3)

| Event Category | Events | Priority |
|---------------|--------|----------|
| **User Actions** | Commands sent, UI interactions | P2 |
| **Connection** | WebSocket/HTTP connection status | P2 |

## Functional Requirements

### FR-1: Event Schema Design

- **FR-1.1**: Define a common event envelope with standard fields:
  - `event_id` (UUID)
  - `event_type` (string, e.g., "battery_status", "command_received")
  - `source` (string, e.g., "ev3", "raspberry_pi", "cloud_function")
  - `timestamp` (TIMESTAMP with microsecond precision)
  - `session_id` (UUID for grouping related events)
  - `payload` (JSON/STRUCT for event-specific data)

- **FR-1.2**: Define specific schemas for each event type (see Data Model section)

- **FR-1.3**: Support schema evolution without breaking existing queries

### FR-2: Data Ingestion

- **FR-2.1**: EV3 must buffer events locally when offline and sync when connected
- **FR-2.2**: Cloud Functions must log all API interactions to BigQuery
- **FR-2.3**: Support batch inserts (recommended for EV3) and streaming inserts (for Cloud Functions)
- **FR-2.4**: Target ingestion latency: < 5 seconds for streaming, < 60 seconds for batch

### FR-3: Data Retention

- **FR-3.1**: Store raw events for 90 days in hot storage
- **FR-3.2**: Archive to cold storage (BigQuery Long-Term Storage) after 90 days
- **FR-3.3**: Partition tables by date for efficient querying and cost management

### FR-4: Query Capabilities

- **FR-4.1**: Support time-range queries for debugging sessions
- **FR-4.2**: Support aggregation queries for analytics (commands/day, battery trends)
- **FR-4.3**: Enable joining across event types (e.g., correlate commands with battery drain)

### FR-5: Security

- **FR-5.1**: Use service accounts with minimal required permissions
- **FR-5.2**: Encrypt data in transit and at rest (BigQuery default)
- **FR-5.3**: No PII or sensitive user data in events

## Data Model

### Core Tables

#### `events` (Main event table - partitioned by date, clustered by source and event_type)

```sql
CREATE TABLE `project.dataset.events` (
  event_id STRING NOT NULL,
  event_type STRING NOT NULL,
  source STRING NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  session_id STRING,
  device_id STRING,
  payload JSON,
  ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(timestamp)
CLUSTER BY source, event_type;
```

### Event Type Schemas (payload structure)

#### Battery Events (`event_type = 'battery_status'`)
```json
{
  "voltage_mv": 7200,
  "current_ma": 450,
  "percentage": 85,
  "battery_type": "rechargeable",
  "is_critical": false
}
```

#### Command Events (`event_type = 'command_received'`)
```json
{
  "command": "forward",
  "params": {
    "speed": 500,
    "duration": 2
  },
  "controller_type": "network_remote",
  "execution_result": "success"
}
```

#### Device Status Events (`event_type = 'device_status'`)
```json
{
  "device_name": "drive_L",
  "port": "A",
  "status": "connected",
  "previous_status": "disconnected"
}
```

#### Motor Events (`event_type = 'motor_status'`)
```json
{
  "motor_name": "drive_L",
  "angle": 1234,
  "speed": 500,
  "is_stalled": false
}
```

#### Sensor Events (`event_type = 'sensor_reading'`)
```json
{
  "sensor_type": "ultrasonic",
  "distance_mm": 250,
  "confidence": 0.95
}
```

#### Terrain Scan Events (`event_type = 'terrain_scan'`)
```json
{
  "scan_id": "uuid",
  "scan_type": "full_360",
  "robot_position": {"x": 0, "y": 0, "heading": 90},
  "point_count": 36,
  "duration_ms": 45000
}
```

#### API Request Events (`event_type = 'api_request'`)
```json
{
  "endpoint": "controlRobot",
  "command": "forward",
  "latency_ms": 150,
  "status_code": 200,
  "client_ip_hash": "abc123",
  "robot_response_time_ms": 120
}
```

#### Error Events (`event_type = 'error'`)
```json
{
  "error_type": "device_error",
  "error_code": "MOTOR_STALL",
  "message": "Left drive motor stalled",
  "stack_trace": null,
  "context": {}
}
```

## Non-Functional Requirements

### NFR-1: Performance
- Batch insert up to 500 events per request
- Streaming insert latency < 5 seconds
- Query performance: simple queries < 5 seconds

### NFR-2: Reliability
- Events must not be lost (at-least-once delivery)
- Local buffering on EV3 when network unavailable
- Retry logic with exponential backoff

### NFR-3: Cost Management
- Use batch inserts where real-time isn't needed (90% cheaper)
- Partition by date to limit query scan
- Cluster by common query predicates

### NFR-4: Scalability
- Support 100+ events/minute from EV3
- Support 1000+ API requests/day from Cloud Functions

## Dependencies

### GCP Services Required
- BigQuery (data warehouse)
- Cloud Functions (existing, needs modification)
- Cloud Pub/Sub (optional, for future streaming)
- Service Account with BigQuery Data Editor role

### Libraries Required
- **EV3 (Python)**: `google-cloud-bigquery` 
- **Cloud Functions (Node.js)**: `@google-cloud/bigquery`
- **Raspberry Pi (Python)**: `google-cloud-bigquery`

## Success Criteria

1. **Data flowing**: Events from EV3 and Cloud Functions visible in BigQuery within 1 minute
2. **Schema complete**: All P0 event types defined and documented
3. **Queryable**: Sample queries working for common use cases
4. **Dashboard**: Basic Looker Studio dashboard showing system health
5. **Documentation**: Complete setup and operational runbooks

## Open Questions

1. **Session management**: How to correlate events across power cycles?
2. **Offline buffering**: How much local storage to allocate on EV3?
3. **Sampling**: Should high-frequency sensor data be sampled or sent in full?
4. **Cost budget**: What's the acceptable monthly BigQuery cost?

## References

- [BigQuery Documentation](https://cloud.google.com/bigquery/docs)
- [BigQuery Best Practices](https://cloud.google.com/bigquery/docs/best-practices-performance-overview)
- [BigQuery Pricing](https://cloud.google.com/bigquery/pricing)
