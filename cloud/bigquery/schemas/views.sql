-- Wrack Telemetry Views
-- Common query patterns for telemetry analytics

-- View: Events from last 24 hours
CREATE OR REPLACE VIEW `wrack_telemetry.events_last_24h` AS
SELECT *
FROM `wrack_telemetry.events`
WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR);

-- View: Battery status events with extracted payload
CREATE OR REPLACE VIEW `wrack_telemetry.battery_events` AS
SELECT
  timestamp,
  device_id,
  session_id,
  JSON_VALUE(payload, '$.voltage_mv') AS voltage_mv,
  JSON_VALUE(payload, '$.voltage_v') AS voltage_v,
  JSON_VALUE(payload, '$.percentage') AS percentage,
  JSON_VALUE(payload, '$.current_ma') AS current_ma,
  JSON_VALUE(payload, '$.battery_type') AS battery_type,
  JSON_VALUE(payload, '$.charging') AS charging
FROM `wrack_telemetry.events`
WHERE event_type = 'battery_status';

-- View: Command events (received and executed)
CREATE OR REPLACE VIEW `wrack_telemetry.command_events` AS
SELECT
  timestamp,
  event_type,
  source,
  device_id,
  session_id,
  JSON_VALUE(payload, '$.command') AS command,
  JSON_VALUE(payload, '$.success') AS success,
  JSON_VALUE(payload, '$.duration_ms') AS duration_ms,
  JSON_VALUE(payload, '$.error_message') AS error_message,
  correlation_id
FROM `wrack_telemetry.events`
WHERE event_type IN ('command_received', 'command_executed');

-- View: Error events
CREATE OR REPLACE VIEW `wrack_telemetry.error_events` AS
SELECT
  timestamp,
  source,
  device_id,
  JSON_VALUE(payload, '$.error_type') AS error_type,
  JSON_VALUE(payload, '$.error_message') AS error_message,
  JSON_VALUE(payload, '$.error_code') AS error_code,
  JSON_VALUE(payload, '$.component') AS component,
  correlation_id
FROM `wrack_telemetry.events`
WHERE event_type = 'error';

-- View: API request events (from Cloud Functions)
CREATE OR REPLACE VIEW `wrack_telemetry.api_requests` AS
SELECT
  timestamp,
  JSON_VALUE(payload, '$.method') AS method,
  JSON_VALUE(payload, '$.endpoint') AS endpoint,
  CAST(JSON_VALUE(payload, '$.status_code') AS INT64) AS status_code,
  CAST(JSON_VALUE(payload, '$.duration_ms') AS FLOAT64) AS duration_ms,
  JSON_VALUE(payload, '$.error_message') AS error_message,
  user_id,
  correlation_id
FROM `wrack_telemetry.events`
WHERE event_type = 'api_request';

-- View: Device status events
CREATE OR REPLACE VIEW `wrack_telemetry.device_status_events` AS
SELECT
  timestamp,
  device_id,
  JSON_VALUE(payload, '$.device_name') AS device_name,
  JSON_VALUE(payload, '$.device_type') AS device_type,
  JSON_VALUE(payload, '$.status') AS status,
  JSON_VALUE(payload, '$.port') AS port,
  JSON_VALUE(payload, '$.error_message') AS error_message
FROM `wrack_telemetry.events`
WHERE event_type = 'device_status';
