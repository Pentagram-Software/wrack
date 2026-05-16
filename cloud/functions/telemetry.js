'use strict';

const functions = require('@google-cloud/functions-framework');
const { BigQuery } = require('@google-cloud/bigquery');
const cors = require('cors');
const { authenticateRequest } = require('./auth');

const corsHandler = cors({
  origin: true,
  methods: ['POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key'],
});

const PROJECT_ID = process.env.BIGQUERY_PROJECT_ID || process.env.GCP_PROJECT_ID || 'wrack-control';
const DATASET_ID = process.env.BIGQUERY_DATASET || 'wrack_telemetry';
const TABLE_ID = process.env.BIGQUERY_TABLE || 'events';

// Lazily created and cached BigQuery client.
let _bigqueryClient = null;

function getBigQueryClient() {
  if (!_bigqueryClient) {
    _bigqueryClient = new BigQuery({ projectId: PROJECT_ID });
  }
  return _bigqueryClient;
}

// Exposed for unit-test injection only.
function _resetBigQueryClient() {
  _bigqueryClient = null;
}

/**
 * Validate a single event object against the wrack_telemetry.events schema.
 * Returns { valid: boolean, errors: string[] }.
 */
function validateEvent(event) {
  const errors = [];

  if (!event.event_id || typeof event.event_id !== 'string' || !event.event_id.trim()) {
    errors.push('event_id is required and must be a non-empty string');
  }

  if (!event.event_type || typeof event.event_type !== 'string' || !event.event_type.trim()) {
    errors.push('event_type is required and must be a non-empty string');
  }

  if (!event.source || typeof event.source !== 'string' || !event.source.trim()) {
    errors.push('source is required and must be a non-empty string');
  }

  if (!event.timestamp) {
    errors.push('timestamp is required');
  } else {
    const ts = new Date(event.timestamp);
    if (isNaN(ts.getTime())) {
      errors.push('timestamp must be a valid ISO 8601 datetime string');
    }
  }

  if (event.payload === undefined || event.payload === null) {
    errors.push('payload is required');
  } else if (typeof event.payload !== 'object' || Array.isArray(event.payload)) {
    errors.push('payload must be a JSON object');
  }

  if (event.tags !== undefined && !Array.isArray(event.tags)) {
    errors.push('tags must be an array of strings when provided');
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Map a validated event object to a BigQuery row, stamping ingested_at.
 */
function prepareRow(event) {
  return {
    event_id: event.event_id,
    event_type: event.event_type,
    source: event.source,
    device_id: event.device_id || null,
    session_id: event.session_id || null,
    timestamp: new Date(event.timestamp).toISOString(),
    ingested_at: new Date().toISOString(),
    // BigQuery JSON columns expect a JSON string in streaming inserts.
    payload: JSON.stringify(event.payload),
    version: event.version || null,
    tags: event.tags || null,
    user_id: event.user_id || null,
    correlation_id: event.correlation_id || null,
  };
}

functions.http('telemetryIngestion', (req, res) => {
  corsHandler(req, res, async () => {
    if (req.method === 'OPTIONS') {
      return res.status(204).send('');
    }

    if (req.method !== 'POST') {
      return res.status(405).json({ error: 'Method not allowed' });
    }

    // Authenticate via X-API-Key header.
    try {
      authenticateRequest(req);
    } catch (authError) {
      return res.status(401).json({ error: authError.message });
    }

    const { events } = req.body || {};

    if (!events) {
      return res.status(400).json({ error: 'events array is required' });
    }
    if (!Array.isArray(events)) {
      return res.status(400).json({ error: 'events must be an array' });
    }
    if (events.length === 0) {
      return res.status(400).json({ error: 'events array must not be empty' });
    }

    // Per-event validation — separate valid from invalid up front.
    const validRows = [];
    const validationFailures = [];

    for (let i = 0; i < events.length; i++) {
      const event = events[i];
      const { valid, errors } = validateEvent(event);

      if (valid) {
        validRows.push({ index: i, row: prepareRow(event) });
      } else {
        validationFailures.push({
          index: i,
          event_id: event.event_id || null,
          errors,
        });
      }
    }

    // If every event failed validation, short-circuit before touching BigQuery.
    if (validRows.length === 0) {
      return res.status(400).json({
        success: false,
        inserted: 0,
        failed: validationFailures.length,
        errors: validationFailures,
      });
    }

    // Batch insert into BigQuery.
    const bq = getBigQueryClient();
    const table = bq.dataset(DATASET_ID).table(TABLE_ID);

    let bqFailures = [];
    let insertedCount = validRows.length;

    try {
      await table.insert(validRows.map((r) => r.row));
    } catch (bqError) {
      if (bqError.name === 'PartialFailureError') {
        // bqError.errors: Array<{ row, errors: [{reason, message, location}] }>
        const rowErrors = bqError.errors || [];

        bqFailures = rowErrors.map((e) => ({
          event_id: e.row ? e.row.event_id : null,
          errors: (e.errors || []).map((err) => err.message || err.reason || 'BigQuery insert error'),
        }));

        const failedEventIds = new Set(bqFailures.map((f) => f.event_id).filter(Boolean));
        insertedCount = validRows.filter((r) => !failedEventIds.has(r.row.event_id)).length;

        console.error('BigQuery PartialFailureError:', JSON.stringify(bqFailures));
      } else {
        console.error('BigQuery insert error:', bqError.message);
        return res.status(500).json({
          success: false,
          error: 'BigQuery insert failed',
          message: bqError.message,
        });
      }
    }

    const allFailures = [...validationFailures, ...bqFailures];
    const totalFailed = allFailures.length;
    const success = totalFailed === 0;
    const statusCode = success ? 200 : 207;

    const responseBody = {
      success,
      inserted: insertedCount,
      failed: totalFailed,
    };

    if (totalFailed > 0) {
      responseBody.errors = allFailures;
    }

    return res.status(statusCode).json(responseBody);
  });
});

module.exports = {
  validateEvent,
  prepareRow,
  getBigQueryClient,
  _resetBigQueryClient,
};
