#!/bin/bash
# Test script for BigQuery telemetry infrastructure
# Inserts a test event and queries it back

set -e

PROJECT_ID="${GCP_PROJECT_ID:-wrack-control}"
DATASET="wrack_telemetry"
TABLE="events"

echo "Testing BigQuery telemetry infrastructure..."
echo "Project: ${PROJECT_ID}"
echo ""

# Generate a unique event ID for this test
EVENT_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

echo "1. Inserting test event (event_id: ${EVENT_ID})..."
bq query --use_legacy_sql=false --project_id="${PROJECT_ID}" <<EOF
INSERT INTO \`${PROJECT_ID}.${DATASET}.${TABLE}\`
  (event_id, event_type, source, timestamp, ingested_at, payload, version, device_id)
VALUES
  ('${EVENT_ID}',
   'battery_status',
   'ev3',
   CURRENT_TIMESTAMP(),
   CURRENT_TIMESTAMP(),
   JSON '{"voltage_mv": 7200, "percentage": 85, "battery_type": "rechargeable"}',
   '1.0.0',
   'ev3-test-001')
EOF

echo ""
echo "2. Querying test event..."
bq query --use_legacy_sql=false --project_id="${PROJECT_ID}" <<EOF
SELECT
  event_id,
  event_type,
  source,
  device_id,
  timestamp,
  JSON_VALUE(payload, '$.voltage_mv') as voltage_mv,
  JSON_VALUE(payload, '$.percentage') as percentage
FROM \`${PROJECT_ID}.${DATASET}.${TABLE}\`
WHERE event_id = '${EVENT_ID}'
EOF

echo ""
echo "3. Testing battery_events view..."
bq query --use_legacy_sql=false --project_id="${PROJECT_ID}" <<EOF
SELECT *
FROM \`${PROJECT_ID}.${DATASET}.battery_events\`
WHERE DATE(timestamp) = CURRENT_DATE()
ORDER BY timestamp DESC
LIMIT 5
EOF

echo ""
echo "4. Checking table stats..."
bq query --use_legacy_sql=false --project_id="${PROJECT_ID}" <<EOF
SELECT
  COUNT(*) as total_events,
  COUNT(DISTINCT event_type) as unique_event_types,
  COUNT(DISTINCT source) as unique_sources,
  MIN(timestamp) as oldest_event,
  MAX(timestamp) as newest_event
FROM \`${PROJECT_ID}.${DATASET}.${TABLE}\`
WHERE DATE(timestamp) >= CURRENT_DATE() - 7
EOF

echo ""
echo "✓ Test completed successfully!"
echo ""
echo "You can now:"
echo "  - View events: bq query --use_legacy_sql=false 'SELECT * FROM \`${PROJECT_ID}.${DATASET}.events\` WHERE DATE(timestamp) = CURRENT_DATE() LIMIT 10'"
echo "  - Delete test event: bq query --use_legacy_sql=false 'DELETE FROM \`${PROJECT_ID}.${DATASET}.${TABLE}\` WHERE event_id = \"${EVENT_ID}\"'"
echo ""
