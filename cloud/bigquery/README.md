# Wrack Telemetry - BigQuery Infrastructure

This directory contains the BigQuery infrastructure for the Wrack robot telemetry system.

## Overview

The telemetry system collects events from:
- **EV3 Robot** (`ev3`) - Battery status, command execution, device status
- **Raspberry Pi** (`rpi`) - Video stream health, vision pipeline metrics
- **Cloud Functions** (`cloud_functions`) - API requests, errors
- **Web Client** (`web`) - User interactions
- **iOS Client** (`ios`) - User interactions

All events are stored in a centralized BigQuery dataset with proper partitioning and retention policies.

## Structure

```
cloud/bigquery/
├── README.md              # This file
├── deploy.sh              # Deployment script for dataset, tables, and views
├── setup-iam.sh           # Service account and IAM setup (PEN-155)
└── schemas/
    ├── events.sql         # Main events table schema
    └── views.sql          # Analytical views
```

## Schema Design

### Events Table

**Table**: `wrack_telemetry.events`

**Key fields**:
- `event_id` - UUID for each event
- `event_type` - Type of event (battery_status, command_received, etc.)
- `source` - Where the event came from (ev3, rpi, cloud_functions, web, ios)
- `timestamp` - Event creation time (UTC)
- `payload` - JSON with event-specific data

**Optimizations**:
- **Partitioned** by `DATE(timestamp)` for efficient time-range queries
- **Clustered** by `source` and `event_type` for fast filtering
- **90-day expiration** on partitions for cost control
- **Partition filter required** to prevent expensive full-table scans

### Views

Pre-built views for common queries:
- `events_last_24h` - Recent events
- `battery_events` - Battery status with extracted fields
- `command_events` - Command tracking (received → executed)
- `error_events` - Error monitoring
- `api_requests` - Cloud Functions performance
- `device_status_events` - Hardware health

## Deployment

### Prerequisites

1. Google Cloud SDK installed with `bq` CLI
2. Authenticated with appropriate GCP project:
   ```bash
   gcloud auth login
   gcloud config set project wrack-control
   ```
3. Permissions: `bigquery.datasets.create`, `bigquery.tables.create`

### Deploy

```bash
cd cloud/bigquery
./deploy.sh
```

The script will:
1. Create the `wrack_telemetry` dataset in `europe-west3`
2. Create the `events` table with partitioning and clustering
3. Create analytical views
4. Verify the deployment

### Configuration

Environment variables (optional):
- `GCP_PROJECT_ID` - GCP project ID (default: `wrack-control`)

Example:
```bash
GCP_PROJECT_ID=wrack-control-dev ./deploy.sh
```

## Usage

### Querying Events

Always include a partition filter (date range) for best performance:

```sql
-- Events from today
SELECT *
FROM `wrack-control.wrack_telemetry.events`
WHERE DATE(timestamp) = CURRENT_DATE()
LIMIT 100;

-- Battery events from last 7 days
SELECT *
FROM `wrack-control.wrack_telemetry.battery_events`
WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY timestamp DESC;

-- Command success rate by device
SELECT
  device_id,
  COUNT(*) as total_commands,
  COUNTIF(success = 'true') as successful,
  ROUND(COUNTIF(success = 'true') / COUNT(*) * 100, 2) as success_rate_pct
FROM `wrack-control.wrack_telemetry.command_events`
WHERE event_type = 'command_executed'
  AND DATE(timestamp) >= CURRENT_DATE() - 7
GROUP BY device_id;
```

### Inserting Events

Events are inserted via:
1. **Cloud Functions** - Telemetry ingestion endpoint (PEN-158)
2. **Direct BigQuery API** - From EV3/RPi using service account (PEN-155)

Example insertion (requires service account):
```bash
bq query --use_legacy_sql=false '
INSERT INTO `wrack-control.wrack_telemetry.events`
  (event_id, event_type, source, timestamp, ingested_at, payload, version)
VALUES
  (GENERATE_UUID(), "battery_status", "ev3", CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(),
   JSON '{"voltage_mv": 7200, "percentage": 85}', "1.0.0")
'
```

## Cost Management

**Estimated costs** (based on 100K events/day):

| Resource | Size | Cost/month (approx) |
|----------|------|---------------------|
| Storage (90 days) | ~10 GB | $0.20 |
| Queries | ~1 TB scanned/month | $5.00 |
| Streaming inserts | 100K/day | $0.50 |
| **Total** | | **~$5.70/month** |

**Cost controls**:
- 90-day partition expiration (automatic deletion)
- Partition filter requirement (prevents full scans)
- Clustering reduces query costs
- JSON payload avoids schema evolution costs

## Monitoring

### Check table size
```bash
bq show --format=prettyjson wrack-control:wrack_telemetry.events | grep numBytes
```

### Check partition info
```bash
bq query --use_legacy_sql=false '
SELECT
  partition_id,
  total_rows,
  total_logical_bytes / 1024 / 1024 as size_mb
FROM `wrack-control.wrack_telemetry.INFORMATION_SCHEMA.PARTITIONS`
WHERE table_name = "events"
ORDER BY partition_id DESC
LIMIT 10
'
```

### Query performance
```sql
-- Slowest query types
SELECT
  JSON_VALUE(payload, '$.event_type') as event_type,
  COUNT(*) as count,
  AVG(TIMESTAMP_DIFF(ingested_at, timestamp, MILLISECOND)) as avg_latency_ms
FROM `wrack-control.wrack_telemetry.events`
WHERE DATE(timestamp) = CURRENT_DATE()
GROUP BY event_type
ORDER BY avg_latency_ms DESC;
```

## Related Tickets

- **PEN-154**: Create BigQuery dataset and events table ✅ (this directory)
- **PEN-155**: Create service account for telemetry writes (see `setup-iam.sh`)
- **PEN-156**: Define event schemas and validation (see `shared/telemetry-types/`)
- **PEN-158**: Create telemetry ingestion Cloud Function

## Troubleshooting

### "Table already exists" error
This is safe to ignore. The deployment is idempotent and will skip existing resources.

### "Permission denied" error
Ensure your user/service account has these roles:
- `roles/bigquery.dataEditor` (for tables)
- `roles/bigquery.user` (for queries)

### "Partition filter required" error
All queries must include a date filter:
```sql
WHERE DATE(timestamp) >= '2026-05-01'  -- Add this
```

### Cost unexpectedly high
Check for:
- Queries without partition filters (scan entire table)
- Queries without clustering filters (scan all partitions)
- Streaming inserts vs. batch (batch is cheaper)

Run this to find expensive queries:
```bash
bq ls -j -a -n 100  # Show recent jobs
```

## Next Steps

1. **PEN-155**: Run `setup-iam.sh` to create service account
2. **PEN-156**: Define event schemas in `shared/telemetry-types/`
3. **PEN-158**: Create Cloud Function for telemetry ingestion
4. Test insertion and querying

## Resources

- [BigQuery Partitioning](https://cloud.google.com/bigquery/docs/partitioned-tables)
- [BigQuery Clustering](https://cloud.google.com/bigquery/docs/clustered-tables)
- [BigQuery Pricing](https://cloud.google.com/bigquery/pricing)
- [JSON Functions](https://cloud.google.com/bigquery/docs/reference/standard-sql/json_functions)
