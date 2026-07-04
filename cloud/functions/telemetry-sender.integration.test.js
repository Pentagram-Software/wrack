'use strict';

/**
 * Integration tests: TelemetrySender → telemetryIngestion Cloud Function.
 *
 * These tests exercise the `telemetryIngestion` handler with the exact request
 * shape that `TelemetrySender` (clients/web/src/lib/telemetry-sender.ts) produces:
 *  - `source: "web"` events
 *  - batches of up to 100 events per POST
 *  - `X-API-Key` authentication header
 *
 * Unlike `telemetry.test.js` (unit tests), this suite focuses on end-to-end
 * validation of TelemetrySender usage patterns rather than exhaustive handler
 * internals.
 *
 * BigQuery is mocked (as in telemetry.test.js) so no GCP credentials are needed.
 */

// ── Mock infrastructure (mirrors telemetry.test.js conventions) ─────────────

let mockAuthenticateRequest;
let mockInsert;

jest.mock('@google-cloud/functions-framework', () => ({
  http: jest.fn(),
}));

jest.mock('cors', () => () => (req, res, callback) => callback());

jest.mock('./auth', () => ({
  authenticateRequest: jest.fn((...args) => mockAuthenticateRequest(...args)),
}));

jest.mock('@google-cloud/bigquery', () => {
  const BigQuery = jest.fn().mockImplementation(() => ({
    dataset: jest.fn().mockReturnValue({
      table: jest.fn().mockReturnValue({
        insert: (...args) => mockInsert(...args),
      }),
    }),
  }));
  return { BigQuery };
});

const functions = require('@google-cloud/functions-framework');
const { _resetBigQueryClient } = require('./telemetry');

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Build a minimal valid telemetry event as the web client would send it. */
function makeWebEvent(overrides = {}) {
  return {
    event_id: `web-evt-${Math.random().toString(36).slice(2)}`,
    event_type: 'device_status',
    source: 'web',
    timestamp: new Date().toISOString(),
    payload: { device_name: 'browser', status: 'connected' },
    ...overrides,
  };
}

/** Build a batch of `count` valid web events. */
function makeBatch(count, eventOverrides = {}) {
  return Array.from({ length: count }, (_, i) =>
    makeWebEvent({ event_id: `web-evt-${i + 1}`, ...eventOverrides }),
  );
}

function makeReq(options = {}) {
  return {
    method: options.method || 'POST',
    headers: options.headers || { 'x-api-key': 'your-secret-api-key' },
    body: options.body !== undefined ? options.body : {},
    connection: { remoteAddress: '127.0.0.1' },
  };
}

function makeRes() {
  const res = {
    statusCode: null,
    data: null,
    status(code) {
      this.statusCode = code;
      return this;
    },
    json(data) {
      this.data = data;
      return this;
    },
    send(body) {
      this.data = body;
      return this;
    },
  };
  jest.spyOn(res, 'status');
  jest.spyOn(res, 'json');
  return res;
}

function invokeHandler(handler, req, res) {
  return new Promise((resolve) => {
    const origJson = res.json.bind(res);
    res.json = jest.fn((...args) => {
      origJson(...args);
      resolve();
      return res;
    });
    const origSend = res.send.bind(res);
    res.send = jest.fn((...args) => {
      origSend(...args);
      resolve();
      return res;
    });
    handler(req, res);
  });
}

// ── Setup ─────────────────────────────────────────────────────────────────────

let telemetryHandler;

beforeAll(() => {
  const calls = functions.http.mock.calls;
  const telemetryCalls = calls.filter((c) => c[0] === 'telemetryIngestion');
  expect(telemetryCalls.length).toBeGreaterThan(0);
  telemetryHandler = telemetryCalls[0][1];
});

beforeEach(() => {
  jest.clearAllMocks();
  mockAuthenticateRequest = jest.fn().mockReturnValue({ authenticated: true });
  mockInsert = jest.fn().mockResolvedValue([]);
  _resetBigQueryClient();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('TelemetrySender integration — single-event batch', () => {
  test('sends one web event and receives 200 success', async () => {
    const req = makeReq({ body: { events: [makeWebEvent()] } });
    const res = makeRes();
    await invokeHandler(telemetryHandler, req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.success).toBe(true);
    expect(res.data.inserted).toBe(1);
    expect(res.data.failed).toBe(0);
  });
});

describe('TelemetrySender integration — max batch (100 events)', () => {
  test('sends a full 100-event batch and receives 200 success', async () => {
    const events = makeBatch(100);
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(telemetryHandler, req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.success).toBe(true);
    expect(res.data.inserted).toBe(100);
    expect(res.data.failed).toBe(0);

    // BigQuery should have been called once with all 100 rows
    expect(mockInsert).toHaveBeenCalledTimes(1);
    expect(mockInsert.mock.calls[0][0]).toHaveLength(100);
  });

  test('BigQuery rows for web events have correct source and serialised payload', async () => {
    const events = makeBatch(3);
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(telemetryHandler, req, res);

    const rows = mockInsert.mock.calls[0][0];
    rows.forEach((row) => {
      // Rows are wrapped as { insertId, json } with raw:true for BQ idempotency.
      expect(row.insertId).toBeDefined();
      expect(row.json.source).toBe('web');
      expect(typeof row.json.payload).toBe('string');
      expect(JSON.parse(row.json.payload)).toMatchObject({
        device_name: 'browser',
        status: 'connected',
      });
      expect(row.json.ingested_at).toBeDefined();
    });
  });
});

describe('TelemetrySender integration — authentication', () => {
  test('returns 401 when X-API-Key header is missing', async () => {
    mockAuthenticateRequest = jest.fn().mockImplementation(() => {
      throw new Error('API key is required');
    });
    const req = makeReq({ headers: {} });
    const res = makeRes();
    await invokeHandler(telemetryHandler, req, res);

    expect(res.statusCode).toBe(401);
    expect(res.data.error).toMatch(/API key/i);
  });

  test('returns 401 for an invalid API key', async () => {
    mockAuthenticateRequest = jest.fn().mockImplementation(() => {
      throw new Error('Invalid API key');
    });
    const req = makeReq({ headers: { 'x-api-key': 'wrong-key' } });
    const res = makeRes();
    await invokeHandler(telemetryHandler, req, res);

    expect(res.statusCode).toBe(401);
  });
});

describe('TelemetrySender integration — mixed valid/invalid events', () => {
  test('returns 207 when batch contains both valid and invalid events', async () => {
    const events = [
      makeWebEvent({ event_id: 'web-valid-1' }),
      { source: 'web' }, // missing event_id, event_type, timestamp, payload
      makeWebEvent({ event_id: 'web-valid-2' }),
      { event_type: 'error' }, // missing event_id, source, timestamp, payload
    ];
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(telemetryHandler, req, res);

    expect(res.statusCode).toBe(207);
    expect(res.data.success).toBe(false);
    expect(res.data.inserted).toBe(2);
    expect(res.data.failed).toBe(2);
  });
});

describe('TelemetrySender integration — request body validation', () => {
  test('returns 400 when events array is empty', async () => {
    const req = makeReq({ body: { events: [] } });
    const res = makeRes();
    await invokeHandler(telemetryHandler, req, res);

    expect(res.statusCode).toBe(400);
  });

  test('returns 400 when events field is missing', async () => {
    const req = makeReq({ body: {} });
    const res = makeRes();
    await invokeHandler(telemetryHandler, req, res);

    expect(res.statusCode).toBe(400);
    expect(res.data.error).toMatch(/events/i);
  });
});

describe('TelemetrySender integration — event field mapping', () => {
  test('optional envelope fields are preserved in BigQuery row when provided', async () => {
    const event = makeWebEvent({
      session_id: 'sess-abc',
      device_id: 'browser-001',
      version: '1.0.0',
      tags: ['production'],
      user_id: 'user-42',
      correlation_id: 'corr-xyz',
    });
    const req = makeReq({ body: { events: [event] } });
    const res = makeRes();
    await invokeHandler(telemetryHandler, req, res);

    expect(res.statusCode).toBe(200);
    const row = mockInsert.mock.calls[0][0][0];
    // Row is wrapped as { insertId, json } with raw:true for BQ idempotency.
    expect(row.json.session_id).toBe('sess-abc');
    expect(row.json.device_id).toBe('browser-001');
    expect(row.json.version).toBe('1.0.0');
    expect(row.json.tags).toEqual(['production']);
    expect(row.json.user_id).toBe('user-42');
    expect(row.json.correlation_id).toBe('corr-xyz');
  });

  test('optional envelope fields default to null when absent', async () => {
    const event = {
      event_id: 'minimal-1',
      event_type: 'connection_status',
      source: 'web',
      timestamp: new Date().toISOString(),
      payload: { status: 'connected' },
    };
    const req = makeReq({ body: { events: [event] } });
    const res = makeRes();
    await invokeHandler(telemetryHandler, req, res);

    const row = mockInsert.mock.calls[0][0][0];
    // Row is wrapped as { insertId, json } with raw:true for BQ idempotency.
    expect(row.json.session_id).toBeNull();
    expect(row.json.device_id).toBeNull();
    expect(row.json.version).toBeNull();
    // tags is REPEATED (ARRAY<STRING>) — BigQuery rejects null/empty for a
    // REPEATED field, so the key is omitted entirely rather than set to null.
    expect('tags' in row.json).toBe(false);
    expect(row.json.user_id).toBeNull();
    expect(row.json.correlation_id).toBeNull();
  });
});
