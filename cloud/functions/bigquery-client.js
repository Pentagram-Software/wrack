'use strict';

/**
 * BigQuery client wrapper for Wrack telemetry.
 *
 * Provides fire-and-forget telemetry ingestion via BigQuery streaming inserts.
 * All public functions return result objects and never throw — callers are
 * responsible for deciding whether to log or ignore failures.
 *
 * Environment variables:
 *   BIGQUERY_PROJECT_ID  - GCP project ID (required to enable; omit to disable)
 *   BIGQUERY_DATASET     - BigQuery dataset ID (default: 'wrack_telemetry')
 *   BIGQUERY_TABLE       - BigQuery table ID   (default: 'events')
 */

const { BigQuery } = require('@google-cloud/bigquery');

const MAX_RETRIES = 3;
const INITIAL_RETRY_DELAY_MS = 200;

// HTTP status codes that warrant a retry
const RETRYABLE_STATUS_CODES = new Set([429, 500, 502, 503, 504]);

// Module-level singletons (lazy-initialised)
let _bigquery = null;
let _table = null;

// ---------------------------------------------------------------------------
// Public helpers
// ---------------------------------------------------------------------------

/**
 * Returns true when all required BigQuery environment variables are present.
 * Inserts are silently skipped when this returns false.
 */
function isEnabled() {
  return Boolean(process.env.BIGQUERY_PROJECT_ID);
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _getTable() {
  if (!_table) {
    const projectId = process.env.BIGQUERY_PROJECT_ID;
    const datasetId = process.env.BIGQUERY_DATASET || 'wrack_telemetry';
    const tableId = process.env.BIGQUERY_TABLE || 'events';

    _bigquery = new BigQuery({ projectId });
    _table = _bigquery.dataset(datasetId).table(tableId);
  }
  return _table;
}

/**
 * Converts a telemetry event envelope into a BigQuery row object.
 * Adds server-side `ingested_at` timestamp and serialises `payload` to JSON.
 */
function _formatRow(event) {
  return {
    event_id: event.event_id,
    event_type: event.event_type,
    source: event.source,
    device_id: event.device_id ?? null,
    session_id: event.session_id ?? null,
    timestamp: event.timestamp,
    ingested_at: new Date().toISOString(),
    payload: typeof event.payload === 'string'
      ? event.payload
      : JSON.stringify(event.payload),
    version: event.version ?? null,
    tags: Array.isArray(event.tags) ? event.tags : null,
    user_id: event.user_id ?? null,
    correlation_id: event.correlation_id ?? null,
  };
}

/**
 * Returns true for errors that may be resolved by retrying (rate limits,
 * transient server-side failures).
 */
function _isRetryableError(err) {
  if (!err) return false;

  if (typeof err.code === 'number' && RETRYABLE_STATUS_CODES.has(err.code)) {
    return true;
  }

  // gRPC / message-based detection
  if (typeof err.message === 'string') {
    const msg = err.message.toLowerCase();
    return (
      msg.includes('unavailable') ||
      msg.includes('rate limit') ||
      msg.includes('quota exceeded') ||
      msg.includes('backend error')
    );
  }

  return false;
}

function _sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Wraps `table.insert(rows)` with exponential-backoff retry for transient
 * errors.  PartialFailureErrors (schema/data issues on individual rows) are
 * not retried and are re-thrown immediately.
 */
async function _insertWithRetry(rows) {
  const table = _getTable();
  let lastError;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      await table.insert(rows);
      return;
    } catch (err) {
      lastError = err;

      // PartialFailureError means the HTTP call succeeded but some rows were
      // rejected by BigQuery.  Retrying won't help.
      if (err.name === 'PartialFailureError') {
        throw err;
      }

      if (attempt < MAX_RETRIES && _isRetryableError(err)) {
        await _sleep(INITIAL_RETRY_DELAY_MS * Math.pow(2, attempt));
        continue;
      }

      throw err;
    }
  }

  throw lastError;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Inserts a batch of telemetry event envelopes into BigQuery.
 *
 * Never throws. Returns a result object:
 *   { success: true,  inserted: N, failed: 0 }
 *   { success: false, inserted: N, failed: M, error: string, errors?: [] }
 *
 * @param {object[]} events - Array of telemetry event envelopes.
 * @returns {Promise<{success: boolean, inserted: number, failed: number, error?: string, errors?: any[]}>}
 */
async function insertEvents(events) {
  if (!Array.isArray(events) || events.length === 0) {
    return { success: true, inserted: 0, failed: 0 };
  }

  if (!isEnabled()) {
    console.warn('[bigquery-client] BIGQUERY_PROJECT_ID not set — telemetry disabled');
    return {
      success: false,
      inserted: 0,
      failed: events.length,
      error: 'BigQuery not configured: BIGQUERY_PROJECT_ID is not set',
    };
  }

  const rows = events.map(_formatRow);

  try {
    await _insertWithRetry(rows);
    return { success: true, inserted: events.length, failed: 0 };
  } catch (err) {
    if (err.name === 'PartialFailureError') {
      const failedRows = err.errors || [];
      const failedCount = failedRows.length;
      const insertedCount = events.length - failedCount;
      console.error('[bigquery-client] Partial insert failure:', JSON.stringify(failedRows));
      return {
        success: false,
        inserted: insertedCount,
        failed: failedCount,
        error: err.message,
        errors: failedRows,
      };
    }

    console.error('[bigquery-client] Insert failed after retries:', err.message);
    return { success: false, inserted: 0, failed: events.length, error: err.message };
  }
}

/**
 * Inserts a single telemetry event envelope into BigQuery.
 *
 * Never throws. Returns the same result shape as `insertEvents`.
 *
 * @param {object} event - A telemetry event envelope.
 * @returns {Promise<{success: boolean, inserted: number, failed: number, error?: string}>}
 */
async function insertEvent(event) {
  if (!event || typeof event !== 'object' || Array.isArray(event)) {
    return {
      success: false,
      inserted: 0,
      failed: 1,
      error: 'Invalid event: must be a non-null object',
    };
  }
  return insertEvents([event]);
}

// ---------------------------------------------------------------------------
// Test helpers (not part of the public API)
// ---------------------------------------------------------------------------

/** Resets module-level BigQuery singletons (for use in tests only). */
function _reset() {
  _bigquery = null;
  _table = null;
}

module.exports = {
  isEnabled,
  insertEvent,
  insertEvents,
  // Exported for testing
  _formatRow,
  _isRetryableError,
  _reset,
};
