'use strict';

/**
 * Pure field-mapping logic for the health-leg push function (PEN-228):
 * turns a validated `type: "health"` telemetry event into the two OTLP
 * shapes Grafana Cloud's gateway understands — gauge metric points (Mimir)
 * and a single structured log record (Loki). Kept free of any OTLP client/
 * network code so it's trivially unit-testable and reusable regardless of
 * how the caller chooses to export the result.
 */

const { SeverityNumber } = require('@opentelemetry/api-logs');

// device_status.json's `status` enum values that represent a problem worth
// surfacing above INFO in Loki/alerting — "connected"/"initializing" are
// routine and stay at INFO.
const DEVICE_STATUS_WARN_STATES = new Set(['error', 'disconnected', 'stalled']);

function _isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

/**
 * Attributes shared by both the metric data points and the log record for
 * a given event — everything needed to identify which device/session/source
 * produced it, omitting fields that are null/absent rather than sending
 * them as empty-string attributes.
 */
function _commonAttributes(event) {
  const attributes = {
    event_type: event.event_type,
    source: event.source,
  };
  if (event.device_id) attributes.device_id = event.device_id;
  if (event.session_id) attributes.session_id = event.session_id;
  return attributes;
}

/**
 * Flatten the numeric (and boolean, coerced to 1/0) fields of a health
 * record's payload into OTLP gauge data points — one metric per field,
 * named `wrack.<event_type>.<field>`. Non-numeric fields (strings, nested
 * objects, arrays — e.g. device_status's `status`) don't produce a metric;
 * they're still captured in full by mapEventToLogRecord() below, so no
 * payload data is dropped, just not double-represented as a gauge.
 *
 * @param {object} event  A validated telemetry event envelope (type: "health").
 * @returns {Array<{name: string, value: number, attributes: object}>}
 */
function mapEventToMetricPoints(event) {
  const payload = (event && event.payload) || {};
  const attributes = _commonAttributes(event);

  return Object.entries(payload)
    .filter(([, value]) => _isFiniteNumber(value) || typeof value === 'boolean')
    .map(([field, value]) => ({
      name: `wrack.${event.event_type}.${field}`,
      value: typeof value === 'boolean' ? (value ? 1 : 0) : value,
      attributes,
    }));
}

/**
 * Determine OTLP severity for a health record. Defaults to INFO; elevated
 * for event_type "error" and for device_status records in a problem state,
 * so Grafana/Loki severity filters and alert rules ([PEN-199]) can act on
 * them without parsing the JSON body.
 */
function _severityForEvent(event) {
  if (event.event_type === 'error') {
    return { severityNumber: SeverityNumber.ERROR, severityText: 'ERROR' };
  }
  if (
    event.event_type === 'device_status' &&
    DEVICE_STATUS_WARN_STATES.has(event.payload && event.payload.status)
  ) {
    return { severityNumber: SeverityNumber.WARN, severityText: 'WARN' };
  }
  return { severityNumber: SeverityNumber.INFO, severityText: 'INFO' };
}

/**
 * Map a health record to a single OTLP log record. The full payload is
 * carried as the structured log body (JSON string) — unlike the metric
 * points, nothing here is dropped for non-numeric fields.
 *
 * @param {object} event
 * @returns {{
 *   body: string,
 *   severityNumber: number,
 *   severityText: string,
 *   attributes: object,
 *   timestampMs: number
 * }}
 */
function mapEventToLogRecord(event) {
  const { severityNumber, severityText } = _severityForEvent(event);
  const parsedTimestamp = event.timestamp ? Date.parse(event.timestamp) : NaN;

  return {
    body: JSON.stringify((event && event.payload) || {}),
    severityNumber,
    severityText,
    attributes: {
      ..._commonAttributes(event),
      event_id: event.event_id,
      ...(event.correlation_id ? { correlation_id: event.correlation_id } : {}),
    },
    timestampMs: Number.isNaN(parsedTimestamp) ? Date.now() : parsedTimestamp,
  };
}

module.exports = {
  mapEventToMetricPoints,
  mapEventToLogRecord,
  _severityForEvent,
  _commonAttributes,
};
