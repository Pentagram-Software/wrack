-- Wrack Telemetry Events Table Schema
-- Stores all telemetry events from EV3, Raspberry Pi, Cloud Functions, and clients

CREATE TABLE IF NOT EXISTS `wrack_telemetry.events` (
  -- Event identification
  event_id STRING NOT NULL OPTIONS(description="Unique event identifier (UUID)"),
  event_type STRING NOT NULL OPTIONS(description="Type of event (battery_status, command_received, etc.)"),

  -- Source tracking
  source STRING NOT NULL OPTIONS(description="Event source (ev3, rpi, cloud_functions, web, ios)"),
  device_id STRING OPTIONS(description="Unique device identifier (e.g., ev3-001, rpi-camera-01)"),
  session_id STRING OPTIONS(description="Session identifier for grouping related events"),

  -- Temporal data
  timestamp TIMESTAMP NOT NULL OPTIONS(description="Event creation time at source (UTC)"),
  ingested_at TIMESTAMP NOT NULL OPTIONS(description="BigQuery ingestion timestamp (server time)"),

  -- Event payload
  payload JSON NOT NULL OPTIONS(description="Event-specific data as JSON"),

  -- Metadata
  version STRING OPTIONS(description="Event schema version (for evolution)"),
  tags ARRAY<STRING> OPTIONS(description="Additional tags for filtering"),

  -- Context (optional)
  user_id STRING OPTIONS(description="User identifier if applicable"),
  correlation_id STRING OPTIONS(description="For tracing across systems")
)
PARTITION BY DATE(timestamp)
CLUSTER BY source, event_type
OPTIONS(
  description="Telemetry events from Wrack robot system components",
  partition_expiration_days=90,
  require_partition_filter=true
);
