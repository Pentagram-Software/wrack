'use strict';

/**
 * Reusable BigQuery client wrapper for Wrack telemetry.
 *
 * Design principles:
 *  - Opt-in / fail-safe: omitting BIGQUERY_PROJECT_ID silently disables the
 *    client so robot-control functions are never blocked by telemetry.
 *  - Never throws: both insertEvent and insertEvents always return a result
 *    object so callers can log/ignore failures without try/catch boilerplate.
 *  - Lazy singleton: the BigQuery client is created on first use.
 *  - Retry: exponential back-off for transient 429 / 5xx / UNAVAILABLE errors
 *    (up to MAX_RETRIES attempts).
 *  - PartialFailureError handling: per-row error reasons are inspected.
 *    Rows with retryable reasons (backendError, rateLimitExceeded, etc.) are
 *    retried separately; rows with non-retryable reasons (invalid schema, etc.)
 *    are reported immediately without retrying.
 *  - Idempotent retries: each row is sent with its event_id as the BigQuery
 *    streaming-insert deduplication key (insertId), so retrying after a
 *    transient failure cannot produce duplicate rows within BigQuery's ~1-min
 *    dedup window.
 */

const { BigQuery } = require('@google-cloud/bigquery');

const MAX_RETRIES = 3;
const BASE_DELAY_MS = 1000;

// Lazily-created singleton BigQuery client.
let _client = null;

// Read env vars dynamically so unit tests can set them in beforeEach without
// needing to re-require the module.
function _projectId() {
  return process.env.BIGQUERY_PROJECT_ID;
}
function _datasetId() {
  return process.env.BIGQUERY_DATASET || 'wrack_telemetry';
}
function _tableId() {
  return process.env.BIGQUERY_TABLE || 'events';
}

// Overridable sleep function — replaced with a no-op in unit tests so retries
// complete instantly without actually waiting.
let _sleepFn = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// ─── Exported helpers (also used by tests) ──────────────────────────────────

/**
 * Returns true when the required BIGQUERY_PROJECT_ID env var is set.
 * When false, all insert operations are silently skipped.
 */
function isEnabled() {
  return Boolean(_projectId());
}

/**
 * Format a telemetry event object into a BigQuery streaming-insert row.
 * Stamps ingested_at and serialises payload to a JSON string (required by the
 * BigQuery JSON column type when using the streaming insert API).
 *
 * The returned object is the row data. Before calling table.insert() the row
 * is wrapped as {insertId: row.event_id, json: row} for deduplication.
 *
 * @param {object} event  Validated telemetry event envelope.
 * @returns {object}  Row data (not yet wrapped with insertId).
 */
function _formatRow(event) {
  const row = {
    event_id: event.event_id,
    event_type: event.event_type,
    source: event.source,
    device_id: event.device_id || null,
    session_id: event.session_id || null,
    timestamp: new Date(event.timestamp).toISOString(),
    ingested_at: new Date().toISOString(),
    payload: JSON.stringify(event.payload),
    version: event.version || null,
    user_id: event.user_id || null,
    correlation_id: event.correlation_id || null,
  };
  // `tags` is a REPEATED (ARRAY<STRING>) column. BigQuery's streaming insert
  // API rejects an explicit `null` or `[]` for a REPEATED field ("Field value
  // of tags cannot be empty") — the key must be omitted entirely unless there
  // is a real, non-empty array to write.
  if (Array.isArray(event.tags) && event.tags.length > 0) {
    row.tags = event.tags;
  }
  return row;
}

/**
 * Returns true for errors that are worth retrying (transient infra problems).
 * Returns false for data/auth errors that will not improve with retries.
 *
 * @param {Error} error
 * @returns {boolean}
 */
function _isRetryableError(error) {
  if (!error) return false;

  const status = error.code || error.statusCode || error.status;
  if (status === 429) return true;
  if (typeof status === 'number' && status >= 500 && status < 600) return true;

  const message = (error.message || '').toLowerCase();
  if (message.includes('unavailable')) return true;
  if (message.includes('rate limit') || message.includes('ratelimitexceeded')) return true;
  if (message.includes('quota exceeded') || message.includes('quotaexceeded')) return true;
  if (message.includes('backenderror') || message.includes('internal error')) return true;

  // Check per-row error reasons returned by the BigQuery API.
  if (error.errors && Array.isArray(error.errors)) {
    return error.errors.some((e) => {
      const reason = (e.reason || '').toLowerCase();
      return (
        reason === 'backenderror' ||
        reason === 'ratelimitexceeded' ||
        reason === 'internalerror' ||
        reason === 'unavailable'
      );
    });
  }

  return false;
}

/**
 * Returns true for BigQuery per-row error reasons that are transient and worth
 * retrying.
 *
 * @param {string} reason  Per-row reason string from BigQuery PartialFailureError.
 * @returns {boolean}
 */
function _isRetryableReason(reason) {
  if (!reason) return false;
  const r = reason.toLowerCase();
  return (
    r === 'backenderror' ||
    r === 'ratelimitexceeded' ||
    r === 'internalerror' ||
    r === 'unavailable'
  );
}

// ─── Private helpers ─────────────────────────────────────────────────────────

function _getClient() {
  if (!_client) {
    _client = new BigQuery({ projectId: _projectId() });
  }
  return _client;
}

/**
 * Extract the row data from a PartialFailureError entry.
 * When rows are sent as {insertId, json}, e.row is the wrapper object;
 * when mocked in tests as plain objects, e.row is the data directly.
 *
 * @param {object} e  One entry from PartialFailureError.errors.
 * @returns {object}  The underlying row data object.
 */
function _rowDataFromError(e) {
  return e.row && e.row.json ? e.row.json : (e.row || {});
}

/**
 * Insert rows into BigQuery with exponential-backoff retry for transient
 * errors.
 *
 * Rows are sent using the {insertId, json} streaming-insert format so that
 * retries are idempotent (BigQuery deduplicates within ~1 minute by insertId).
 *
 * For PartialFailureError: per-row reasons are inspected.  Rows with retryable
 * reasons are retried; rows with non-retryable reasons are surfaced
 * immediately without further attempts.
 *
 * @param {object[]} rows     Pre-formatted BigQuery row data objects.
 * @param {number}   attempt  Current attempt index (0-based).
 * @returns {Promise<{success: boolean, partialFailure?: boolean, error?: Error}>}
 */
async function _insertWithRetry(rows, attempt = 0) {
  const client = _getClient();
  const table = client.dataset(_datasetId()).table(_tableId());

  // Wrap rows with insertId for idempotent retries.
  // event_id is the stable per-event dedupe key; fall back to a timestamp-
  // based key for events that lack one.
  const rowsWithId = rows.map((row) => ({
    insertId: row.event_id || `${row.event_type || 'evt'}-${Date.now()}`,
    json: row,
  }));

  try {
    await table.insert(rowsWithId);
    return { success: true };
  } catch (error) {
    if (error.name === 'PartialFailureError') {
      const rowErrors = error.errors || [];

      // Separate failed rows into retryable (transient) and non-retryable (bad data).
      const retryableRowErrors = rowErrors.filter((e) =>
        (e.errors || []).some((re) => _isRetryableReason(re.reason))
      );
      const permanentRowErrors = rowErrors.filter(
        (e) => !(e.errors || []).some((re) => _isRetryableReason(re.reason))
      );

      if (retryableRowErrors.length > 0 && attempt < MAX_RETRIES) {
        const retryableIds = new Set(
          retryableRowErrors.map((e) => _rowDataFromError(e).event_id).filter(Boolean)
        );
        const retryRows = rows.filter((r) => retryableIds.has(r.event_id));

        const delayMs = BASE_DELAY_MS * Math.pow(2, attempt);
        await _sleepFn(delayMs);
        const retryResult = await _insertWithRetry(retryRows, attempt + 1);

        if (permanentRowErrors.length > 0) {
          const permanentError = new Error('Some rows failed permanently');
          permanentError.name = 'PartialFailureError';
          permanentError.errors = permanentRowErrors;
          return { success: false, partialFailure: true, error: permanentError };
        }
        return retryResult;
      }

      return { success: false, partialFailure: true, error };
    }

    if (_isRetryableError(error) && attempt < MAX_RETRIES) {
      const delayMs = BASE_DELAY_MS * Math.pow(2, attempt);
      await _sleepFn(delayMs);
      return _insertWithRetry(rows, attempt + 1);
    }

    return { success: false, partialFailure: false, error };
  }
}

/** Parse BigQuery PartialFailureError into a structured errors array. */
function _parsePartialFailure(bqError) {
  return (bqError.errors || []).map((e) => {
    const rowData = _rowDataFromError(e);
    return {
      event_id: rowData.event_id || null,
      errors: (e.errors || []).map((err) => err.message || err.reason || 'BigQuery insert error'),
    };
  });
}

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Insert a single telemetry event into BigQuery.
 *
 * Never throws — all errors are returned in the result object so callers can
 * log and continue without try/catch.
 *
 * @param {object} event  Telemetry event envelope (must have event_id,
 *   event_type, source, timestamp, payload).
 * @returns {Promise<{
 *   success: boolean,
 *   skipped?: boolean,
 *   reason?: string,
 *   partialFailure?: boolean,
 *   errors?: object[],
 *   error?: string
 * }>}
 */
async function insertEvent(event) {
  if (!isEnabled()) {
    return {
      success: false,
      skipped: true,
      reason: 'BigQuery telemetry not configured (BIGQUERY_PROJECT_ID not set)',
    };
  }

  try {
    const row = _formatRow(event);
    const result = await _insertWithRetry([row]);

    if (!result.success) {
      if (result.partialFailure) {
        const errors = _parsePartialFailure(result.error);
        console.error('[bigquery-client] insertEvent PartialFailureError:', JSON.stringify(errors));
        return { success: false, partialFailure: true, errors };
      }
      console.error('[bigquery-client] insertEvent failed:', result.error.message);
      return { success: false, error: result.error.message };
    }

    return { success: true };
  } catch (error) {
    console.error('[bigquery-client] insertEvent unexpected error:', error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Batch-insert multiple telemetry events into BigQuery in a single API call.
 *
 * Never throws — all errors are returned in the result object.
 *
 * @param {object[]} events  Array of telemetry event envelopes.
 * @returns {Promise<{
 *   success: boolean,
 *   inserted?: number,
 *   skipped?: boolean,
 *   reason?: string,
 *   partialFailure?: boolean,
 *   errors?: object[],
 *   error?: string
 * }>}
 */
async function insertEvents(events) {
  if (!isEnabled()) {
    return {
      success: false,
      skipped: true,
      reason: 'BigQuery telemetry not configured (BIGQUERY_PROJECT_ID not set)',
    };
  }

  if (!Array.isArray(events) || events.length === 0) {
    return { success: false, error: 'events must be a non-empty array' };
  }

  try {
    const rows = events.map(_formatRow);
    const result = await _insertWithRetry(rows);

    if (!result.success) {
      if (result.partialFailure) {
        const errors = _parsePartialFailure(result.error);
        console.error('[bigquery-client] insertEvents PartialFailureError:', JSON.stringify(errors));
        return { success: false, partialFailure: true, errors };
      }
      console.error('[bigquery-client] insertEvents failed:', result.error.message);
      return { success: false, error: result.error.message };
    }

    return { success: true, inserted: events.length };
  } catch (error) {
    console.error('[bigquery-client] insertEvents unexpected error:', error.message);
    return { success: false, error: error.message };
  }
}

// ─── Test injection hooks ─────────────────────────────────────────────────────

/** Reset the cached BigQuery client singleton (for unit-test isolation). */
function _resetClient() {
  _client = null;
}

/**
 * Replace the internal sleep function (for unit tests so retry delays complete
 * instantly without actual wall-clock time).
 *
 * @param {function(number): Promise<void>} fn
 */
function _setSleepFn(fn) {
  _sleepFn = fn;
}

module.exports = {
  isEnabled,
  insertEvent,
  insertEvents,
  _formatRow,
  _isRetryableError,
  _isRetryableReason,
  _resetClient,
  _setSleepFn,
};
