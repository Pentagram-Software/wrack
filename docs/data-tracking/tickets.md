# BigQuery Data Tracking - Ticket Definitions

## Overview

This document defines the implementation tickets for the BigQuery data tracking system. Tickets are organized by epic/phase with dependencies clearly marked.

## Epic Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 1: FOUNDATION                                │
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │ Epic 1       │    │ Epic 2       │    │ Epic 3       │                  │
│  │ BigQuery     │───►│ Cloud Fn     │───►│ EV3          │                  │
│  │ Setup        │    │ Telemetry    │    │ Telemetry    │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 2: ENRICHMENT                                │
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐                                       │
│  │ Epic 4       │    │ Epic 5       │                                       │
│  │ Raspberry Pi │    │ Analytics    │                                       │
│  │ Telemetry    │    │ Dashboards   │                                       │
│  └──────────────┘    └──────────────┘                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Epic 1: BigQuery Infrastructure Setup

**Goal**: Set up BigQuery dataset, tables, and access controls

### PEN-100: Create BigQuery Dataset and Events Table
**Type**: Task  
**Priority**: P0  
**Estimate**: Small  
**Dependencies**: None

**Description**:
Set up the BigQuery infrastructure for telemetry data storage.

**Acceptance Criteria**:
- [ ] Dataset `wrack_telemetry` created in EU region
- [ ] Events table created with proper schema (see `requirements.md`)
- [ ] Table partitioned by `timestamp` (daily)
- [ ] Table clustered by `source`, `event_type`
- [ ] DDL scripts committed to `cloud/bigquery/schemas/`

**Technical Notes**:
- Use `bq` CLI or Terraform for reproducibility
- Consider adding table expiration (90 days) for cost management

---

### PEN-101: Create Service Account for Telemetry Writes
**Type**: Task  
**Priority**: P0  
**Estimate**: Small  
**Dependencies**: PEN-100

**Description**:
Create a dedicated service account with minimal permissions for writing telemetry data.

**Acceptance Criteria**:
- [ ] Service account `telemetry-writer@wrack-control.iam.gserviceaccount.com` created
- [ ] `BigQuery Data Editor` role granted on `wrack_telemetry` dataset only
- [ ] Service account key generated and stored securely
- [ ] Documentation updated with setup instructions

---

### PEN-102: Define Event Schemas and Validation
**Type**: Task  
**Priority**: P0  
**Estimate**: Medium  
**Dependencies**: PEN-100

**Description**:
Define JSON schemas for all event types and create validation utilities.

**Acceptance Criteria**:
- [ ] JSON Schema definitions for all P0 events:
  - `battery_status`
  - `command_received`
  - `command_executed`
  - `device_status`
  - `error`
  - `api_request`
- [ ] Shared type definitions in `shared/telemetry-types/`
- [ ] Python validation module in `robot/controller/telemetry/schemas.py`
- [ ] TypeScript validation in `cloud/functions/schemas.ts`
- [ ] Unit tests for validation logic

---

## Epic 2: Cloud Functions Telemetry

**Goal**: Add telemetry logging to Cloud Functions and create ingestion endpoint

### PEN-110: Add BigQuery Client to Cloud Functions
**Type**: Task  
**Priority**: P0  
**Estimate**: Small  
**Dependencies**: PEN-100, PEN-101

**Description**:
Add BigQuery client library and wrapper to Cloud Functions.

**Acceptance Criteria**:
- [ ] `@google-cloud/bigquery` added to `package.json`
- [ ] `bigquery-client.js` created with:
  - Connection initialization
  - `insertEvent(event)` method
  - `insertEvents(events[])` batch method
  - Error handling and retry logic
- [ ] Unit tests for client wrapper
- [ ] Environment variables documented

---

### PEN-111: Create Telemetry Ingestion Cloud Function
**Type**: Story  
**Priority**: P0  
**Estimate**: Medium  
**Dependencies**: PEN-110, PEN-102

**Description**:
Create a new Cloud Function that accepts batched events from EV3/RPi and inserts them into BigQuery.

**Acceptance Criteria**:
- [ ] `telemetryIngestion` function created in `telemetry.js`
- [ ] Accepts POST with `{ events: [...] }` body
- [ ] Validates API key in `X-API-Key` header
- [ ] Validates each event against schema
- [ ] Enriches events with `ingested_at` timestamp
- [ ] Inserts to BigQuery (batch insert for cost)
- [ ] Returns `{ success: true, inserted: N, failed: M }`
- [ ] Error response includes details for failed events
- [ ] Deployed to `europe-central2` region

**Technical Notes**:
```javascript
// Example request
POST /telemetryIngestion
X-API-Key: <telemetry-key>
{
  "events": [
    {
      "event_id": "uuid",
      "event_type": "battery_status",
      "source": "ev3",
      "timestamp": "2026-03-22T10:00:00Z",
      "session_id": "session-uuid",
      "device_id": "ev3-001",
      "payload": { "voltage_mv": 7200, "percentage": 85 }
    }
  ]
}
```

---

### PEN-112: Add Telemetry Logging to controlRobot Function
**Type**: Story  
**Priority**: P0  
**Estimate**: Small  
**Dependencies**: PEN-110

**Description**:
Log all API requests to BigQuery from the existing `controlRobot` function.

**Acceptance Criteria**:
- [ ] Each request logged with:
  - Command name
  - Parameters (sanitized)
  - Latency (total, robot response time)
  - Status code
  - Client IP hash
  - Error message (if any)
- [ ] Logging is non-blocking (fire and forget)
- [ ] Errors in logging don't affect command execution
- [ ] Tests verify logging doesn't impact latency

---

## Epic 3: EV3 Telemetry Collection

**Goal**: Implement telemetry collection on the EV3 robot

### PEN-120: Create Telemetry Module Structure
**Type**: Task  
**Priority**: P0  
**Estimate**: Small  
**Dependencies**: PEN-102

**Description**:
Create the telemetry module structure in `robot/controller/`.

**Acceptance Criteria**:
- [ ] `telemetry/` directory created with:
  - `__init__.py`
  - `collector.py`
  - `sender.py`
  - `schemas.py`
  - `tests/`
- [ ] `requests` library added to `requirements.txt`
- [ ] Module importable from main controller

---

### PEN-121: Implement TelemetryCollector
**Type**: Story  
**Priority**: P0  
**Estimate**: Medium  
**Dependencies**: PEN-120

**Description**:
Implement the event collection and buffering component.

**Acceptance Criteria**:
- [ ] `TelemetryCollector` class with:
  - `collect(event_type, **data)` method
  - In-memory buffer (configurable max size, default 500)
  - Thread-safe operations
  - Session ID management
- [ ] Event formatting to standard schema
- [ ] Buffer overflow handling (FIFO drop)
- [ ] Disk persistence when buffer reaches threshold
- [ ] Unit tests with >80% coverage

**Technical Notes**:
```python
class TelemetryCollector:
    def __init__(self, max_buffer_size=500, flush_threshold=100):
        self.buffer = []
        self.session_id = str(uuid.uuid4())
        
    def collect(self, event_type: str, **payload):
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "source": "ev3",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "session_id": self.session_id,
            "device_id": self._get_device_id(),
            "payload": payload
        }
        self.buffer.append(event)
```

---

### PEN-122: Implement TelemetrySender
**Type**: Story  
**Priority**: P0  
**Estimate**: Medium  
**Dependencies**: PEN-121, PEN-111

**Description**:
Implement the component that sends batched events to Cloud Functions.

**Acceptance Criteria**:
- [ ] `TelemetrySender` class with:
  - `send(events)` method
  - HTTP POST to telemetry endpoint
  - API key authentication
  - Retry with exponential backoff (max 3 retries)
  - Batch size limit (100 events per request)
- [ ] Background sending (non-blocking)
- [ ] Offline detection and graceful degradation
- [ ] Unit tests with mocked HTTP
- [ ] Integration test with local Cloud Function

---

### PEN-123: Hook Telemetry into EventHandler
**Type**: Story  
**Priority**: P0  
**Estimate**: Small  
**Dependencies**: PEN-121

**Description**:
Modify `EventHandler` to automatically collect telemetry.

**Acceptance Criteria**:
- [ ] `EventHandler.set_telemetry_collector()` method added
- [ ] All triggered events optionally forwarded to collector
- [ ] Event filtering (not all events need telemetry)
- [ ] No impact on existing event handling
- [ ] Tests verify backward compatibility

---

### PEN-124: Add Battery and Motor Status Collection
**Type**: Story  
**Priority**: P0  
**Estimate**: Small  
**Dependencies**: PEN-123

**Description**:
Implement periodic collection of battery and motor status.

**Acceptance Criteria**:
- [ ] Battery status collected every 60 seconds
- [ ] Motor status collected every 10 seconds
- [ ] Status changes (device connect/disconnect) collected immediately
- [ ] Collection intervals configurable
- [ ] Tests verify collection timing

---

### PEN-125: Add Command Telemetry
**Type**: Story  
**Priority**: P0  
**Estimate**: Small  
**Dependencies**: PEN-123

**Description**:
Log all commands received and executed.

**Acceptance Criteria**:
- [ ] `command_received` event logged when command arrives
- [ ] `command_executed` event logged after execution
- [ ] Includes controller type (PS4, network remote)
- [ ] Includes execution result and timing
- [ ] Works for both PS4 and network remote commands

---

## Epic 4: Raspberry Pi Telemetry (Phase 2)

**Goal**: Add telemetry collection to Raspberry Pi edge components

### PEN-130: Create RPi Telemetry Module
**Type**: Story  
**Priority**: P1  
**Estimate**: Medium  
**Dependencies**: PEN-121

**Description**:
Port telemetry collection to Raspberry Pi components.

**Acceptance Criteria**:
- [ ] Telemetry module in `edge/vision/telemetry/`
- [ ] Reuses schemas from `shared/telemetry-types/`
- [ ] Same API as EV3 telemetry
- [ ] Configured for RPi environment

---

### PEN-131: Vision Pipeline Telemetry
**Type**: Story  
**Priority**: P1  
**Estimate**: Medium  
**Dependencies**: PEN-130

**Description**:
Log vision/ML inference results to BigQuery.

**Acceptance Criteria**:
- [ ] Object detection events logged
- [ ] Includes: class, confidence, bounding box
- [ ] Frame metadata included
- [ ] Configurable logging frequency (not every frame)

---

### PEN-132: Video Stream Health Telemetry
**Type**: Story  
**Priority**: P2  
**Estimate**: Small  
**Dependencies**: PEN-130

**Description**:
Log video streaming health metrics.

**Acceptance Criteria**:
- [ ] Stream start/stop events
- [ ] Frame drop counts (periodic)
- [ ] Encoding stats (bitrate, FPS)
- [ ] Connected clients count

---

## Epic 5: Analytics and Dashboards

**Goal**: Create queries and dashboards for system monitoring

### PEN-140: Create Standard Queries
**Type**: Task  
**Priority**: P1  
**Estimate**: Small  
**Dependencies**: PEN-112, PEN-125

**Description**:
Create commonly used SQL queries and save as BigQuery views.

**Acceptance Criteria**:
- [ ] Views created for:
  - Events per hour by source
  - Battery level over time
  - Commands by type (daily)
  - Error frequency
  - Session durations
- [ ] Queries optimized for partitioned tables
- [ ] Documented in `cloud/bigquery/views/`

---

### PEN-141: Create Looker Studio Dashboard
**Type**: Story  
**Priority**: P1  
**Estimate**: Medium  
**Dependencies**: PEN-140

**Description**:
Create a basic monitoring dashboard in Looker Studio.

**Acceptance Criteria**:
- [ ] Dashboard created with:
  - Battery level chart (time series)
  - Commands per hour (bar chart)
  - Error count (scorecard)
  - Session activity (timeline)
- [ ] Dashboard shared with team
- [ ] Auto-refresh enabled (hourly)

---

### PEN-142: Set Up Monitoring Alerts
**Type**: Task  
**Priority**: P1  
**Estimate**: Small  
**Dependencies**: PEN-112

**Description**:
Create Cloud Monitoring alerts for telemetry health.

**Acceptance Criteria**:
- [ ] Alert: Telemetry ingestion errors > 10/min
- [ ] Alert: No events for 10 minutes (during session)
- [ ] Alert: BigQuery insert latency > 30s
- [ ] Notifications via email/Slack

---

## Ticket Summary Table

| ID | Title | Epic | Priority | Dependencies |
|----|-------|------|----------|--------------|
| PEN-100 | Create BigQuery Dataset and Events Table | 1 | P0 | - |
| PEN-101 | Create Service Account | 1 | P0 | PEN-100 |
| PEN-102 | Define Event Schemas and Validation | 1 | P0 | PEN-100 |
| PEN-110 | Add BigQuery Client to Cloud Functions | 2 | P0 | PEN-100, PEN-101 |
| PEN-111 | Create Telemetry Ingestion Cloud Function | 2 | P0 | PEN-110, PEN-102 |
| PEN-112 | Add Telemetry Logging to controlRobot | 2 | P0 | PEN-110 |
| PEN-120 | Create Telemetry Module Structure | 3 | P0 | PEN-102 |
| PEN-121 | Implement TelemetryCollector | 3 | P0 | PEN-120 |
| PEN-122 | Implement TelemetrySender | 3 | P0 | PEN-121, PEN-111 |
| PEN-123 | Hook Telemetry into EventHandler | 3 | P0 | PEN-121 |
| PEN-124 | Add Battery and Motor Status Collection | 3 | P0 | PEN-123 |
| PEN-125 | Add Command Telemetry | 3 | P0 | PEN-123 |
| PEN-130 | Create RPi Telemetry Module | 4 | P1 | PEN-121 |
| PEN-131 | Vision Pipeline Telemetry | 4 | P1 | PEN-130 |
| PEN-132 | Video Stream Health Telemetry | 4 | P2 | PEN-130 |
| PEN-140 | Create Standard Queries | 5 | P1 | PEN-112, PEN-125 |
| PEN-141 | Create Looker Studio Dashboard | 5 | P1 | PEN-140 |
| PEN-142 | Set Up Monitoring Alerts | 5 | P1 | PEN-112 |

## Suggested Implementation Order

### Sprint 1: Foundation
1. PEN-100: BigQuery Dataset
2. PEN-101: Service Account
3. PEN-102: Event Schemas

### Sprint 2: Cloud Functions
4. PEN-110: BigQuery Client
5. PEN-111: Telemetry Ingestion Function
6. PEN-112: controlRobot Logging

### Sprint 3: EV3 Collection
7. PEN-120: Module Structure
8. PEN-121: TelemetryCollector
9. PEN-122: TelemetrySender
10. PEN-123: EventHandler Hook

### Sprint 4: EV3 Events + Analytics
11. PEN-124: Battery/Motor Collection
12. PEN-125: Command Telemetry
13. PEN-140: Standard Queries
14. PEN-142: Monitoring Alerts

### Sprint 5: Dashboards + RPi (Phase 2)
15. PEN-141: Looker Studio Dashboard
16. PEN-130: RPi Telemetry Module
17. PEN-131: Vision Pipeline Telemetry
18. PEN-132: Video Stream Health
