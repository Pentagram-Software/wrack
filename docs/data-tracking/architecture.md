# Cloud Data Tracking Architecture

## Overview

This document describes the architecture for collecting telemetry and events from Wrack system components and ingesting them into Google BigQuery for analytics and monitoring.

> **Note:** BigQuery was selected after evaluating alternatives including InfluxDB, PostgreSQL/TimescaleDB, Firestore, and ClickHouse. See the [Technology Alternatives Analysis](requirements.md#technology-alternatives-analysis) in the requirements document for the full evaluation.

## System Context

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                                    │
├──────────────────┬──────────────────┬──────────────────┬───────────────────┤
│   EV3 Robot      │  Raspberry Pi    │  Cloud Functions │   Web/iOS Clients │
│   (Python)       │  (Python)        │  (Node.js)       │   (TS/Swift)      │
│                  │                  │                  │                   │
│  • Battery       │  • Vision/ML     │  • API requests  │  • User actions   │
│  • Commands      │  • Stream health │  • Connections   │  • Connections    │
│  • Motors        │  • System stats  │  • Errors        │                   │
│  • Sensors       │                  │                  │                   │
│  • Errors        │                  │                  │                   │
└────────┬─────────┴────────┬─────────┴────────┬─────────┴─────────┬─────────┘
         │                  │                  │                   │
         │ HTTP/HTTPS       │ HTTP/HTTPS       │ Direct API        │ HTTP/HTTPS
         │ (batch)          │ (batch)          │ (streaming)       │ (batch)
         ▼                  ▼                  ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        INGESTION LAYER                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Cloud Functions: telemetryIngestion                      │   │
│  │                                                                       │   │
│  │  • Validates event schema                                            │   │
│  │  • Enriches with server timestamp                                    │   │
│  │  • Authenticates source (API key)                                    │   │
│  │  • Routes to BigQuery                                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ BigQuery API                           │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    BigQuery Dataset: wrack_telemetry                 │   │
│  │                                                                       │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │   │
│  │  │   events    │  │   events    │  │   events    │   (partitioned   │   │
│  │  │ (2026-03-22)│  │ (2026-03-21)│  │ (2026-03-20)│    by date)      │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ SQL Queries
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ANALYTICS LAYER                                       │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │  Looker Studio  │  │  Custom Queries │  │  Future: ML     │             │
│  │  Dashboards     │  │  (ad-hoc)       │  │  Pipelines      │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Monorepo Structure

### New Directories and Files

```
wrack/
├── cloud/
│   ├── bigquery/                          # NEW: BigQuery schemas and setup
│   │   ├── schemas/
│   │   │   └── events.sql                 # Table DDL
│   │   ├── migrations/
│   │   │   └── 001_initial_schema.sql     # Initial migration
│   │   └── README.md
│   │
│   └── functions/
│       ├── index.js                       # MODIFY: Add telemetry logging
│       ├── telemetry.js                   # NEW: Telemetry ingestion function
│       ├── bigquery-client.js             # NEW: BigQuery client wrapper
│       └── package.json                   # MODIFY: Add @google-cloud/bigquery
│
├── robot/
│   └── controller/
│       ├── telemetry/                     # NEW: Telemetry module
│       │   ├── __init__.py
│       │   ├── collector.py               # Event collection and buffering
│       │   ├── sender.py                  # HTTP client to Cloud Functions
│       │   ├── schemas.py                 # Event type definitions
│       │   └── tests/
│       │       └── test_telemetry.py
│       ├── event_handler/
│       │   └── event_handler.py           # MODIFY: Hook telemetry collection
│       └── requirements.txt               # MODIFY: Add requests library
│
├── edge/
│   └── vision/                            # FUTURE: Phase 2
│       └── telemetry/
│           ├── __init__.py
│           └── collector.py
│
└── shared/
    └── telemetry-types/                   # NEW: Shared event type definitions
        ├── typescript/
        │   └── events.ts
        └── python/
            └── events.py
```

### File Responsibilities

| File | Responsibility |
|------|---------------|
| `cloud/bigquery/schemas/events.sql` | BigQuery table DDL with partitioning and clustering |
| `cloud/bigquery/migrations/*.sql` | Schema migrations for evolution |
| `cloud/functions/telemetry.js` | HTTP Cloud Function for ingesting events |
| `cloud/functions/bigquery-client.js` | Wrapper for BigQuery insert operations |
| `robot/controller/telemetry/collector.py` | Collects events from EV3, buffers locally |
| `robot/controller/telemetry/sender.py` | Sends batched events to Cloud Functions |
| `shared/telemetry-types/` | Type definitions shared across languages |

## Data Flow

### Phase 1: EV3 → BigQuery

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EV3 ROBOT                                          │
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │ PS4Controller │    │RemoteControl │    │ DeviceManager│                  │
│  │              │    │              │    │              │                  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                  │
│         │                   │                   │                           │
│         │ events            │ events            │ events                    │
│         ▼                   ▼                   ▼                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    EventHandler (existing)                           │   │
│  │                         │                                            │   │
│  │                         │ hook                                       │   │
│  │                         ▼                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │              TelemetryCollector (new)                        │    │   │
│  │  │                                                              │    │   │
│  │  │  • Captures events from EventHandler                         │    │   │
│  │  │  • Formats into standard schema                              │    │   │
│  │  │  • Buffers in memory (max 500 events)                        │    │   │
│  │  │  • Persists to disk when buffer full                         │    │   │
│  │  │  • Triggers background send                                  │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ trigger every 30s or 100 events       │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    TelemetrySender (new)                             │   │
│  │                                                                       │   │
│  │  • Reads from buffer/disk                                            │   │
│  │  • Batches events (max 100 per request)                              │   │
│  │  • HTTP POST to Cloud Function                                       │   │
│  │  • Retry with exponential backoff                                    │   │
│  │  • Clears sent events from buffer                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS POST (batched events)
                                    │ Header: X-API-Key
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     CLOUD FUNCTION: telemetryIngestion                       │
│                                                                              │
│  1. Validate API key                                                         │
│  2. Validate event schema                                                    │
│  3. Enrich with ingestion timestamp                                         │
│  4. Insert to BigQuery (streaming for real-time, batch for cost)            │
│  5. Return success/failure count                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ BigQuery Streaming/Batch Insert
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BigQuery: events table                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Phase 1: Cloud Functions → BigQuery (Direct)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     CLOUD FUNCTION: controlRobot (existing)                  │
│                                                                              │
│  Request received                                                            │
│       │                                                                      │
│       ├───► Process command (existing logic)                                │
│       │                                                                      │
│       └───► Log to BigQuery (new)                                           │
│               │                                                              │
│               ▼                                                              │
│       ┌─────────────────────────────────────────────────────────────┐       │
│       │  bigquery-client.logEvent({                                  │       │
│       │    event_type: 'api_request',                               │       │
│       │    source: 'cloud_function',                                │       │
│       │    payload: { command, latency, status }                    │       │
│       │  })                                                          │       │
│       └─────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Event Collection Strategy

### EV3: Hook into EventHandler

The existing `EventHandler` class will be modified to support telemetry:

```python
class EventHandler:
    def __init__(self):
        self.handlers = {}
        self.telemetry_collector = None  # NEW
    
    def set_telemetry_collector(self, collector):  # NEW
        """Hook telemetry collection into event system."""
        self.telemetry_collector = collector
    
    def trigger(self, event_name, *args, **kwargs):
        # Existing: call registered handlers
        for handler in self.handlers.get(event_name, []):
            handler(*args, **kwargs)
        
        # NEW: Also send to telemetry
        if self.telemetry_collector:
            self.telemetry_collector.collect(event_name, *args, **kwargs)
```

### Events to Collect

| Source | Event | Trigger Point | Payload |
|--------|-------|---------------|---------|
| EV3 | `battery_status` | Timer (every 60s) | voltage, current, percentage |
| EV3 | `command_received` | RemoteController.handle_command | command, params, source |
| EV3 | `command_executed` | After motor action | command, result, duration |
| EV3 | `device_status` | DeviceManager status change | device, status |
| EV3 | `motor_status` | Timer (every 10s) | motors state |
| EV3 | `sensor_reading` | On significant change | sensor type, value |
| EV3 | `error` | Error handlers | error type, message |
| Cloud | `api_request` | controlRobot function | command, latency, status |
| Cloud | `connection_status` | TCP connect/disconnect | host, success, error |

## Deployment Strategy

### Phase 1 Deployment (EV3 + Cloud Functions)

#### Step 1: BigQuery Setup
```bash
# Create dataset
bq mk --dataset \
  --location=EU \
  --description="Wrack telemetry data" \
  wrack-control:wrack_telemetry

# Create events table
bq query --use_legacy_sql=false < cloud/bigquery/schemas/events.sql
```

#### Step 2: Deploy Telemetry Cloud Function
```bash
cd cloud/functions
npm run deploy:telemetry

# Or using gcloud directly:
gcloud functions deploy telemetryIngestion \
  --runtime nodejs20 \
  --trigger-http \
  --allow-unauthenticated \
  --region europe-central2 \
  --set-env-vars BIGQUERY_DATASET=wrack_telemetry
```

#### Step 3: Modify controlRobot Function
```bash
# Update existing function with BigQuery logging
cd cloud/functions
npm run deploy
```

#### Step 4: Deploy to EV3
```bash
# Copy telemetry module to robot
scp -r robot/controller/telemetry robot@ev3:/home/robot/controller/

# Update requirements
ssh robot@ev3 "cd /home/robot/controller && pip install -r requirements.txt"
```

### Environment Variables

#### Cloud Functions
```bash
# Existing
ROBOT_HOST=<ev3-ip>
ROBOT_PORT=27700
API_KEY=<api-key>

# New
BIGQUERY_PROJECT=wrack-control
BIGQUERY_DATASET=wrack_telemetry
BIGQUERY_TABLE=events
TELEMETRY_API_KEY=<telemetry-api-key>
```

#### EV3 Robot
```bash
# New environment variables for robot
TELEMETRY_ENDPOINT=https://europe-central2-wrack-control.cloudfunctions.net/telemetryIngestion
TELEMETRY_API_KEY=<telemetry-api-key>
TELEMETRY_BATCH_SIZE=100
TELEMETRY_FLUSH_INTERVAL=30
```

## Security

### Authentication

1. **EV3 → Cloud Function**: API key in `X-API-Key` header (same pattern as controlRobot)
2. **Cloud Function → BigQuery**: Service account with `BigQuery Data Editor` role

### Service Account Setup

The service account is created by `cloud/bigquery/setup-iam.sh` (PEN-155). Run it once after `deploy.sh`:

```bash
# Default project (wrack-control), key written to ./telemetry-writer-key.json
bash cloud/bigquery/setup-iam.sh

# Dry run — print commands without executing
bash cloud/bigquery/setup-iam.sh --dry-run
```

The script performs these steps:

```bash
# 1. Create the service account
gcloud iam service-accounts create telemetry-writer \
  --project=wrack-control \
  --display-name="Wrack Telemetry Writer" \
  --description="Writes telemetry events to BigQuery wrack_telemetry dataset."

# 2. Grant BigQuery Data Editor at DATASET level only (not project-level)
#    This is the least-privilege approach: the SA can only read/write data
#    inside wrack_telemetry and cannot touch any other dataset or resource.
bq add-iam-policy-binding \
  --member="serviceAccount:telemetry-writer@wrack-control.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor" \
  wrack-control:wrack_telemetry

# 3. Generate JSON key and store as GitHub Actions secret TELEMETRY_SA_KEY
gcloud iam service-accounts keys create telemetry-writer-key.json \
  --iam-account=telemetry-writer@wrack-control.iam.gserviceaccount.com
gh secret set TELEMETRY_SA_KEY < telemetry-writer-key.json
rm -f telemetry-writer-key.json   # delete local copy immediately
```

See `cloud/bigquery/README.md` for the full setup guide, including options and
verification steps.

### Data Privacy

- No PII collected
- IP addresses are hashed before storage
- Device IDs are internal identifiers only

## Error Handling

### EV3 Telemetry

1. **Network unavailable**: Buffer locally to disk (max 10MB)
2. **Buffer full**: Drop oldest events (FIFO)
3. **API error**: Retry with exponential backoff (max 3 retries)
4. **Invalid event**: Log locally, skip sending

### Cloud Function

1. **BigQuery error**: Return error to client, log to Cloud Logging
2. **Invalid schema**: Return 400 with details
3. **Rate limit**: Use exponential backoff client-side

## Monitoring

### Cloud Monitoring Alerts

1. **Telemetry ingestion failures** > 10/minute
2. **BigQuery insert latency** > 10 seconds
3. **No events received** for 5 minutes (during active session)

### BigQuery Views for Monitoring

```sql
-- Events per source in last hour
CREATE VIEW `wrack_telemetry.events_per_source_hourly` AS
SELECT 
  source,
  event_type,
  COUNT(*) as event_count,
  TIMESTAMP_TRUNC(timestamp, HOUR) as hour
FROM `wrack_telemetry.events`
WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
GROUP BY source, event_type, hour;
```

## Cost Estimation

### BigQuery Costs (EU region)

| Item | Estimate | Monthly Cost |
|------|----------|--------------|
| Storage | 1 GB (90 days) | $0.02/GB = ~$0.02 |
| Streaming inserts | 50K events/day | $0.05/200MB = ~$0.75 |
| Queries | 100 queries/day, 1GB scanned | $5/TB = ~$0.15 |
| **Total** | | **~$1/month** |

### Cost Optimization

1. Use **batch inserts** for EV3 events (90% cheaper than streaming)
2. **Partition by date** to limit query scans
3. **Cluster by source, event_type** for common queries
4. Set **table expiration** for short-term data

## Future Enhancements (Phase 2+)

### Pub/Sub Integration
- Replace direct HTTP with Pub/Sub for better reliability
- Enable multiple subscribers (BigQuery, real-time alerts)

### Dataflow Pipeline
- Real-time aggregations and anomaly detection
- ML feature engineering

### Materialized Views
- Pre-computed aggregations for dashboards
- Reduce query costs for common patterns

## References

- [BigQuery Best Practices](https://cloud.google.com/bigquery/docs/best-practices-performance-overview)
- [Cloud Functions Best Practices](https://cloud.google.com/functions/docs/bestpractices/tips)
- [Telemetry Data Pipeline Patterns](https://cloud.google.com/architecture/telemetry-data-pipeline)
