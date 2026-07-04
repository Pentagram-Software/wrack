'use strict';

/**
 * Non-blocking telemetry logging for the controlRobot Cloud Function.
 *
 * Builds and inserts `api_request` telemetry events into BigQuery using a
 * fire-and-forget pattern. Errors in the logging path are caught and written
 * to stderr so they never propagate to the caller or affect command latency.
 */

const crypto = require('crypto');
const { BigQuery } = require('@google-cloud/bigquery');

const PROJECT_ID = process.env.BIGQUERY_PROJECT_ID || process.env.GCP_PROJECT_ID || 'wrack-control';
const DATASET_ID = process.env.BIGQUERY_DATASET || 'wrack_telemetry';
const TABLE_ID = process.env.BIGQUERY_TABLE || 'events';

let _bqClient = null;

function _getBqClient() {
  if (!_bqClient) {
    _bqClient = new BigQuery({ projectId: PROJECT_ID });
  }
  return _bqClient;
}

/** Reset the cached BigQuery client — exposed for unit-test injection only. */
function _resetBqClient() {
  _bqClient = null;
}

/**
 * Sanitize command parameters before logging.
 *
 * Free-text fields that could contain PII (e.g. the `speak` command's `text`
 * param) are replaced with a length placeholder. All numeric/boolean params
 * (speed, duration, joystick axes, etc.) are safe and pass through unchanged.
 *
 * @param {string|null} command - The robot command name.
 * @param {object|null} params  - The raw params object from the request body.
 * @returns {object|null} A sanitized copy, or null if params is falsy.
 */
function sanitizeParams(command, params) {
  if (!params || typeof params !== 'object' || Array.isArray(params)) {
    return null;
  }
  const safe = { ...params };
  if (command === 'speak' && typeof safe.text === 'string') {
    safe.text = `[${safe.text.length} chars]`;
  }
  return safe;
}

/**
 * Build a telemetry event envelope for an `api_request` event.
 *
 * @param {object} data
 * @param {string}       data.method            - HTTP method of the incoming request (e.g. 'POST', 'GET').
 * @param {string|null}  data.command           - Robot command name (null when request failed before command parsing).
 * @param {object|null}  data.params            - Raw request params (will be sanitized).
 * @param {number}       data.statusCode        - HTTP status code returned to the caller.
 * @param {number}       data.totalLatencyMs    - Total request wall-time in milliseconds.
 * @param {number|null}  data.robotLatencyMs    - Time waiting for EV3 TCP response (null if not reached).
 * @param {string|null}  data.clientIpHash      - SHA-256 hash of the caller identifier.
 * @param {string|null}  data.errorMessage      - Error detail when status >= 400.
 * @returns {object} A valid telemetry event envelope.
 */
function buildApiRequestEvent({
  method = 'POST',
  command,
  params,
  statusCode,
  totalLatencyMs,
  robotLatencyMs,
  clientIpHash,
  errorMessage,
}) {
  return {
    event_id: crypto.randomUUID(),
    event_type: 'api_request',
    source: 'cloud_functions',
    timestamp: new Date().toISOString(),
    payload: {
      endpoint: 'controlRobot',
      method: method,
      command: command != null ? String(command) : null,
      sanitized_params: sanitizeParams(command, params),
      status_code: statusCode,
      latency_ms: totalLatencyMs,
      robot_response_time_ms: robotLatencyMs != null ? robotLatencyMs : null,
      client_ip_hash: clientIpHash || null,
      error_message: errorMessage || null,
    },
  };
}

/**
 * Fire-and-forget: log an `api_request` telemetry event to BigQuery.
 *
 * The function returns synchronously after scheduling the work via
 * `setImmediate`, ensuring it never contributes to request latency. Any
 * errors (build failures, BigQuery errors) are caught and logged to stderr
 * so they cannot affect command execution.
 *
 * @param {object} data          - Same shape as {@link buildApiRequestEvent}.
 * @param {string} [data.method] - HTTP method; defaults to 'POST' if omitted.
 */
function logApiRequest(data) {
  setImmediate(() => {
    let row;
    try {
      const event = buildApiRequestEvent(data);
      // `tags` (REPEATED/ARRAY<STRING>) is deliberately omitted rather than
      // set to null — BigQuery's streaming insert API rejects an explicit
      // null/empty value for a REPEATED field ("Field value of tags cannot
      // be empty"); the key must be absent when there's nothing to write.
      row = {
        event_id: event.event_id,
        event_type: event.event_type,
        source: event.source,
        device_id: null,
        session_id: null,
        timestamp: event.timestamp,
        ingested_at: new Date().toISOString(),
        payload: JSON.stringify(event.payload),
        version: null,
        user_id: null,
        correlation_id: null,
      };
    } catch (buildErr) {
      console.error('[api-telemetry] Failed to build api_request event:', buildErr.message);
      return;
    }

    _getBqClient()
      .dataset(DATASET_ID)
      .table(TABLE_ID)
      .insert([row])
      .catch((insertErr) => {
        console.error('[api-telemetry] Failed to insert api_request event:', insertErr.message);
      });
  });
}

module.exports = {
  logApiRequest,
  buildApiRequestEvent,
  sanitizeParams,
  _resetBqClient,
};
