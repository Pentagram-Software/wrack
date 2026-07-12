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

// Matches DEFAULT_BATCH_SIZE in robot/controller/telemetry/sender.py and
// edge/vision/telemetry/sender.py — no legitimate sender ever constructs a
// larger batch. Without this cap, an authenticated or compromised device
// could submit an arbitrarily large events array, driving unbounded
// validation work, BigQuery payload size/retries, and health-leg fan-out.
const MAX_EVENTS_PER_REQUEST = 100;

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

// True only for a flat object mapping deviceId -> token string — e.g.
// null, an array, or a map with a non-string value all fail this. JSON.parse
// alone doesn't guarantee this shape (`null`, `"hello"`, `["a"]`, and
// `{"ev3-001": 12345}` are all valid JSON), and trusting it uncritically
// isn't just a data-integrity risk: Object.hasOwn(null, deviceId) further
// down actually throws, which would otherwise leak as a misleading 401
// (see validateDeviceAuth) instead of the 503 a malformed secret deserves.
function _isValidDeviceTokensShape(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }
  return Object.values(value).every((v) => typeof v === 'string');
}

async function getDeviceTokens() {
  const isFresh = _deviceTokensCache && Date.now() - _deviceTokensCacheTime < DEVICE_TOKENS_CACHE_TTL_MS;
  if (isFresh) {
    return _deviceTokensCache;
  }
  const client = _getSecretClient();
  const name = `projects/${GCP_PROJECT_ID}/secrets/${DEVICE_TOKENS_SECRET}/versions/latest`;
  const [version] = await client.accessSecretVersion({ name });
  const parsed = JSON.parse(version.payload.data.toString('utf8'));
  if (!_isValidDeviceTokensShape(parsed)) {
    // Thrown here, before caching, so malformed data is never trusted even
    // once — and this propagates through validateDeviceAuth's existing
    // try/catch, which wraps it as a SecretLoadError (503, generic
    // message), the same as any other secret-loading failure.
    throw new Error('device-tokens secret has an unexpected shape (expected a flat object of deviceId -> token strings)');
  }
  _deviceTokensCache = parsed;
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

// Thrown when the device-tokens secret itself couldn't be loaded (missing
// IAM grant, Secret Manager outage, malformed JSON) — distinct from a
// credential mismatch, which is the caller's fault. The HTTP handler uses
// `instanceof SecretLoadError` to tell the two apart: this one must never
// be reported as 401 (wrong info: it's not that the credentials are
// invalid, it's that nothing could be checked) and must never leak the
// underlying exception's message to the caller (may contain internal
// infrastructure detail — project IDs, IAM policy hints, stack traces).
class SecretLoadError extends Error {
  constructor(message, cause) {
    super(message);
    this.name = 'SecretLoadError';
    this.cause = cause;
  }
}

/**
 * Validate the X-Device-Id / X-Device-Token headers against the device-token
 * map. Throws on missing headers or an unknown/mismatched device (generic
 * message, safe to return to the caller as 401), or SecretLoadError if the
 * secret itself couldn't be loaded (must not be treated as 401 — see above).
 */
async function validateDeviceAuth(req) {
  const deviceId = req.headers['x-device-id'];
  const deviceToken = req.headers['x-device-token'];

  if (!deviceId || !deviceToken) {
    throw new Error('X-Device-Id and X-Device-Token headers are required');
  }

  let tokens;
  try {
    tokens = await getDeviceTokens();
  } catch (err) {
    throw new SecretLoadError('Unable to load device credentials', err);
  }

  // `tokens` is a plain object parsed from JSON, so a bare `tokens[deviceId]`
  // also resolves inherited Object.prototype properties — a deviceId of
  // "toString" would resolve to the built-in toString function (truthy),
  // whose stringified form is fixed and predictable, letting an attacker
  // authenticate without ever seeing a real token. Object.hasOwn() restricts
  // the lookup to the secret's actual own keys.
  const expected = Object.hasOwn(tokens, deviceId) ? tokens[deviceId] : undefined;

  if (!expected || !_timingSafeStringEqual(deviceToken, expected)) {
    throw new Error('Invalid device credentials');
  }

  return { deviceId };
}

// Maps a device_id's naming convention to the coarse `source` category
// (mirrors VALID_SOURCES in shared/telemetry-types) that device is allowed
// to submit events as. Authentication only proves *which* device_id is
// calling — it says nothing about the client-supplied `source` field, so
// without this an ev3-001 credential could submit events labeled
// source: "rpi" (or any other value) just as easily as it could have
// spoofed device_id before that was fixed. New device categories need a
// prefix added here — this intentionally doesn't guess.
const DEVICE_ID_SOURCE_PREFIXES = [
  { prefix: 'ev3', source: 'ev3' },
  { prefix: 'rpi', source: 'rpi' },
];

/**
 * Returns the source a device_id is authorized to submit events as, or null
 * if the device_id doesn't match any known naming convention.
 */
function deriveSourceForDeviceId(deviceId) {
  const match = DEVICE_ID_SOURCE_PREFIXES.find((p) => deviceId.startsWith(p.prefix));
  return match ? match.source : null;
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

// A single request's health records were previously fanned out with one
// concurrent fetch per record and no limit — a large batch (from a valid or
// compromised device; nothing upstream caps events.length) could open
// hundreds or thousands of simultaneous outbound connections, exhausting
// this instance's sockets/memory and potentially overwhelming the
// downstream health-leg function. Processing in bounded chunks caps how
// many pushes are ever in flight at once, regardless of batch size.
const HEALTH_PUSH_CONCURRENCY = 20;

// Chunking alone bounds concurrency but not total wall-clock time: chunks
// run sequentially, so a 100-record batch (5 chunks) where every push hits
// its own HEALTH_LEG_FETCH_TIMEOUT_MS could take up to 15s — longer than
// both senders' 10s HTTP timeout, which would make them time out, retry,
// and duplicate-push a batch the ingress actually already accepted. This
// caps the *whole* health leg's time budget, independent of batch size;
// once exceeded, remaining health records are dropped (fail open) rather
// than attempted, same policy as any other health-leg failure.
const HEALTH_LEG_TOTAL_BUDGET_MS = 4000;

async function pushHealthRecords(events) {
  const results = [];
  const deadline = Date.now() + HEALTH_LEG_TOTAL_BUDGET_MS;
  for (let i = 0; i < events.length; i += HEALTH_PUSH_CONCURRENCY) {
    if (Date.now() >= deadline) {
      const remaining = events.length - i;
      console.log(`[ingress] health-leg time budget exceeded — dropping ${remaining} remaining health record(s)`);
      break;
    }
    const chunk = events.slice(i, i + HEALTH_PUSH_CONCURRENCY);
    results.push(...(await Promise.allSettled(chunk.map((event) => pushHealthRecord(event)))));
  }
  return results;
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
      if (authError instanceof SecretLoadError) {
        // Log full detail server-side only — the caller gets a generic
        // message, not the underlying Secret Manager/IAM exception text.
        console.error('[ingress] failed to load device-tokens secret:', authError.cause?.message || authError.message);
        return res.status(503).json({ error: 'Authentication temporarily unavailable' });
      }
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
    if (events.length > MAX_EVENTS_PER_REQUEST) {
      return res
        .status(400)
        .json({ error: `events array must not exceed ${MAX_EVENTS_PER_REQUEST} events per request` });
    }

    // Per-event validation — reuses telemetryIngestion's envelope validator
    // so both endpoints stay consistent without duplicating the rules.
    const validRows = [];
    const validationFailures = [];

    // Computed once — the authenticated device doesn't change per event in
    // a batch, and an unmapped device_id (a new device category provisioned
    // without updating DEVICE_ID_SOURCE_PREFIXES) rejects every event in
    // this request the same way.
    const expectedSource = deriveSourceForDeviceId(authenticatedDeviceId);

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

      if (valid && !expectedSource) {
        errors.push(`no known source mapping for device_id "${authenticatedDeviceId}"`);
      }

      if (valid && errors.length === 0) {
        // Authentication proves who is calling, not who an event claims to
        // be from — client-supplied device_id and source must never be
        // trusted as-is, or one device's token could be used to attribute
        // events to (and poison the data/dashboards of) a different device
        // or device category. The authenticated identity always wins,
        // regardless of what the caller put in the payload.
        event.device_id = authenticatedDeviceId;
        event.source = expectedSource;
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

    // The two legs are deliberately decoupled (PEN-218): health fails open
    // and never retries, analytics retries hard and surfaces failures. They
    // used to run sequentially (await health, then await BigQuery) — but
    // each has its own multi-second worst case (health's own time budget,
    // ~7s; BigQuery's exponential-backoff retries, up to ~7s), and summed
    // sequentially that comfortably exceeds both senders' 10s HTTP timeout,
    // causing the sender to time out and retry a batch the ingress already
    // accepted. Running them concurrently bounds total time to whichever
    // leg is slower, not their sum.
    const healthPromise =
      healthRows.length > 0 ? pushHealthRecords(healthRows.map((r) => r.event)) : Promise.resolve([]);
    const eventPromise = eventRows.length > 0 ? insertEvents(eventRows.map((r) => r.event)) : Promise.resolve(null);

    const [, result] = await Promise.all([healthPromise, eventPromise]);

    // Analytics leg result — health leg counts every record as "inserted"
    // from the caller's point of view regardless of outcome (fail-open), so
    // there's nothing further to process for it here.
    let eventInsertedCount = 0;
    const eventFailures = [];
    let hardFailure = null;

    if (result) {
      if (result.success) {
        eventInsertedCount = eventRows.length;
      } else if (result.partialFailure) {
        const failedIds = new Set((result.errors || []).map((e) => e.event_id).filter(Boolean));
        eventInsertedCount = eventRows.filter((r) => !failedIds.has(r.event.event_id)).length;
        for (const e of result.errors || []) {
          // No `index` field here, deliberately — it's how the EV3/Pi sender
          // (sender.py::_classify_207) tells a permanent validation failure
          // (has index) from a retryable BigQuery failure (event_id only).
          // Adding index here made every BigQuery failure look permanent,
          // so genuinely transient failures were dropped instead of retried.
          eventFailures.push({ event_id: e.event_id, errors: e.errors });
        }
      } else {
        // Hard failure or BigQuery not configured (skipped) — every event
        // row in this batch is reported as failed, but health records that
        // already succeeded above are not affected. No `index` here either,
        // for the same reason: a hard BigQuery failure is exactly the kind
        // of transient condition the sender should retry.
        const message = result.reason || result.error || 'BigQuery insert failed';
        for (const r of eventRows) {
          eventFailures.push({ event_id: r.event.event_id, errors: [message] });
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
  deriveSourceForDeviceId,
  pushHealthRecord,
  getDeviceTokens,
  SecretLoadError,
  _isValidDeviceTokensShape,
  _resetDeviceTokensCache,
  _timingSafeStringEqual,
};
