'use strict';

/**
 * Unified telemetry ingress Cloud Function (PEN-227).
 *
 * Single HTTP endpoint both EV3 and the Raspberry Pi POST batched telemetry
 * to, authenticated per-device (not the shared API_KEY used by controlRobot
 * and telemetryIngestion). Each event's `type` field (health|event, optional,
 * defaults to "event") routes it onward:
 *   - type=event  -> BigQuery, via bigquery-client.js (retry + backoff)
 *   - type=health -> the health-leg push function, via a direct synchronous
 *                    HTTP call. Fails open: a missing HEALTH_LEG_FUNCTION_URL
 *                    or a failed call is logged and dropped, never surfaced
 *                    as a failure to the caller (PEN-218: "a missed metric
 *                    point is low stakes", unlike an analytics event).
 *
 * Accepts the exact same {"events": [...]} batch body shape and returns the
 * same 200/207/400 response shapes as telemetryIngestion, so existing sender
 * retry logic (robot/controller/telemetry/sender.py,
 * edge/vision/telemetry/sender.py) needs no changes beyond pointing at this
 * endpoint and presenting per-device credentials instead of the shared key.
 */

const functions = require('@google-cloud/functions-framework');
const cors = require('cors');
const crypto = require('crypto');
const { SecretManagerServiceClient } = require('@google-cloud/secret-manager');
const { validateEvent } = require('./telemetry');
const { insertEvents } = require('./bigquery-client');

const corsHandler = cors({
  origin: true,
  methods: ['POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'X-Device-Id', 'X-Device-Token'],
});

const GCP_PROJECT_ID = process.env.GCP_PROJECT_ID || process.env.BIGQUERY_PROJECT_ID || 'wrack-control';
const DEVICE_TOKENS_SECRET = process.env.DEVICE_TOKENS_SECRET || 'device-tokens';

// Read dynamically (not captured as a top-level const) so unit tests can
// toggle it per-test via process.env without needing to re-require the
// module — same rationale as bigquery-client.js's _projectId()/_datasetId().
function _healthLegFunctionUrl() {
  return process.env.HEALTH_LEG_FUNCTION_URL || null;
}

// ─── Device-token secret loading (cached across warm invocations) ───────────

let _secretClient = null;
function _getSecretClient() {
  if (!_secretClient) {
    _secretClient = new SecretManagerServiceClient();
  }
  return _secretClient;
}

// Cached secret is re-fetched after this many ms so a rotated/revoked token
// (via setup-device-tokens.sh --rotate) takes effect on already-warm
// instances within a bounded window, instead of living forever until the
// instance happens to cold-start.
const DEVICE_TOKENS_CACHE_TTL_MS = 5 * 60 * 1000;

let _deviceTokensCache = null;
let _deviceTokensCacheTime = 0;

async function getDeviceTokens() {
  const isFresh = _deviceTokensCache && Date.now() - _deviceTokensCacheTime < DEVICE_TOKENS_CACHE_TTL_MS;
  if (isFresh) {
    return _deviceTokensCache;
  }
  const client = _getSecretClient();
  const name = `projects/${GCP_PROJECT_ID}/secrets/${DEVICE_TOKENS_SECRET}/versions/latest`;
  const [version] = await client.accessSecretVersion({ name });
  _deviceTokensCache = JSON.parse(version.payload.data.toString('utf8'));
  _deviceTokensCacheTime = Date.now();
  return _deviceTokensCache;
}

// Exposed for unit-test injection only.
function _resetDeviceTokensCache() {
  _deviceTokensCache = null;
  _deviceTokensCacheTime = 0;
}

function _timingSafeStringEqual(a, b) {
  const bufA = Buffer.from(String(a), 'utf8');
  const bufB = Buffer.from(String(b), 'utf8');
  if (bufA.length !== bufB.length) {
    return false;
  }
  return crypto.timingSafeEqual(bufA, bufB);
}

/**
 * Validate the X-Device-Id / X-Device-Token headers against the device-token
 * map. Throws on missing headers or an unknown/mismatched device.
 */
async function validateDeviceAuth(req) {
  const deviceId = req.headers['x-device-id'];
  const deviceToken = req.headers['x-device-token'];

  if (!deviceId || !deviceToken) {
    throw new Error('X-Device-Id and X-Device-Token headers are required');
  }

  const tokens = await getDeviceTokens();
  const expected = tokens[deviceId];

  if (!expected || !_timingSafeStringEqual(deviceToken, expected)) {
    throw new Error('Invalid device credentials');
  }

  return { deviceId };
}

// ─── Type-field routing ──────────────────────────────────────────────────────

const VALID_RECORD_TYPES = ['health', 'event'];

/**
 * True when the event's `type` field is a value the router understands: the
 * schema declares it as an enum of health/event/absent — a typo or garbage
 * value must not be silently routed to BigQuery as if it were valid.
 */
function isValidTypeField(event) {
  const type = event && event.type;
  return type === undefined || type === null || VALID_RECORD_TYPES.includes(type);
}

/** Resolve an event's coarse record type, defaulting to "event" when absent. */
function resolveType(event) {
  return event && event.type === 'health' ? 'health' : 'event';
}

// A stalled health endpoint must not be able to hold the whole ingress
// request open — that would defeat both "return 200 quickly" and the
// documented fail-open behavior. Bounds each push to a few seconds.
const HEALTH_LEG_FETCH_TIMEOUT_MS = 3000;

/**
 * Push a single health record to the health-leg function. Always fails open:
 * a missing URL, a timeout, or a failed call is logged and swallowed, never
 * thrown.
 */
async function pushHealthRecord(event) {
  const url = _healthLegFunctionUrl();
  if (!url) {
    console.log(`[ingress] HEALTH_LEG_FUNCTION_URL not configured — dropping health record ${event.event_id}`);
    return { success: false, skipped: true };
  }

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
      signal: AbortSignal.timeout(HEALTH_LEG_FETCH_TIMEOUT_MS),
    });
    if (!res.ok) {
      console.error(`[ingress] health leg push responded ${res.status} for event ${event.event_id}`);
      return { success: false, error: `health leg responded ${res.status}` };
    }
    return { success: true };
  } catch (err) {
    console.error(`[ingress] health leg push error for event ${event.event_id} (fail open):`, err.message);
    return { success: false, error: err.message };
  }
}

// ─── HTTP handler ─────────────────────────────────────────────────────────────

functions.http('unifiedIngress', (req, res) => {
  corsHandler(req, res, async () => {
    if (req.method === 'OPTIONS') {
      return res.status(204).send('');
    }

    if (req.method !== 'POST') {
      return res.status(405).json({ error: 'Method not allowed' });
    }

    let authenticatedDeviceId;
    try {
      ({ deviceId: authenticatedDeviceId } = await validateDeviceAuth(req));
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

    // Per-event validation — reuses telemetryIngestion's envelope validator
    // so both endpoints stay consistent without duplicating the rules.
    const validRows = [];
    const validationFailures = [];

    for (let i = 0; i < events.length; i++) {
      const event = events[i];
      const { valid, errors } = validateEvent(event);

      // validateEvent() is shared with telemetryIngestion, which predates
      // and doesn't know about the `type` field, so it's checked separately
      // here rather than in telemetry.js — a typo'd type must be rejected,
      // not silently routed to BigQuery as if it were a valid "event".
      if (valid && !isValidTypeField(event)) {
        errors.push(`type must be one of: ${VALID_RECORD_TYPES.join(', ')} (or absent)`);
      }

      if (valid && errors.length === 0) {
        // Authentication proves who is calling, not who an event claims to
        // be from — a client-supplied device_id must never be trusted as-is,
        // or one device's token could be used to attribute events to (and
        // poison the data/dashboards of) a different device. The
        // authenticated identity always wins, regardless of what the caller
        // put in the payload.
        event.device_id = authenticatedDeviceId;
        validRows.push({ index: i, event, type: resolveType(event) });
      } else {
        validationFailures.push({
          index: i,
          event_id: (event != null && event.event_id) || null,
          errors,
        });
      }
    }

    if (validRows.length === 0) {
      return res.status(400).json({
        success: false,
        inserted: 0,
        failed: validationFailures.length,
        errors: validationFailures,
      });
    }

    const eventRows = validRows.filter((r) => r.type === 'event');
    const healthRows = validRows.filter((r) => r.type === 'health');

    // Health leg: fail open. Every health record counts as inserted from the
    // caller's point of view — downstream push failures are logged, never
    // surfaced, matching PEN-218's "a missed metric point is low stakes".
    if (healthRows.length > 0) {
      await Promise.allSettled(healthRows.map((r) => pushHealthRecord(r.event)));
    }

    // Analytics leg: retries hard, failures are surfaced (losing an
    // analytics event is costlier than missing one health sample).
    let eventInsertedCount = 0;
    const eventFailures = [];
    let hardFailure = null;

    if (eventRows.length > 0) {
      const result = await insertEvents(eventRows.map((r) => r.event));

      if (result.success) {
        eventInsertedCount = eventRows.length;
      } else if (result.partialFailure) {
        const failedIds = new Set((result.errors || []).map((e) => e.event_id).filter(Boolean));
        eventInsertedCount = eventRows.filter((r) => !failedIds.has(r.event.event_id)).length;
        for (const e of result.errors || []) {
          eventFailures.push({
            index: eventRows.find((r) => r.event.event_id === e.event_id)?.index ?? null,
            event_id: e.event_id,
            errors: e.errors,
          });
        }
      } else {
        // Hard failure or BigQuery not configured (skipped) — every event
        // row in this batch is reported as failed, but health records that
        // already succeeded above are not affected.
        const message = result.reason || result.error || 'BigQuery insert failed';
        for (const r of eventRows) {
          eventFailures.push({ index: r.index, event_id: r.event.event_id, errors: [message] });
        }
        hardFailure = message;
      }
    }

    const allFailures = [...validationFailures, ...eventFailures];
    const totalFailed = allFailures.length;
    const totalInserted = healthRows.length + eventInsertedCount;

    if (totalFailed === 0) {
      return res.status(200).json({ success: true, inserted: totalInserted, failed: 0 });
    }

    if (totalInserted === 0 && hardFailure) {
      return res.status(500).json({ success: false, error: 'BigQuery insert failed', message: hardFailure });
    }

    return res.status(207).json({
      success: false,
      inserted: totalInserted,
      failed: totalFailed,
      errors: allFailures,
    });
  });
});

module.exports = {
  validateDeviceAuth,
  resolveType,
  isValidTypeField,
  pushHealthRecord,
  getDeviceTokens,
  _resetDeviceTokensCache,
  _timingSafeStringEqual,
};
