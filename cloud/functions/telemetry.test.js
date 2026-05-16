'use strict';

/**
 * Unit tests for the telemetryIngestion Cloud Function.
 *
 * Strategy:
 *  - Mock @google-cloud/functions-framework so registrations are captured.
 *  - Mock cors to invoke callback synchronously.
 *  - Mock ./auth so we can control authentication success/failure per test.
 *  - Mock @google-cloud/bigquery via a variable-captured insert function so
 *    per-test behaviour can be changed without re-requiring the module.
 */

// --- Module-level mock variables (reassigned in beforeEach) ---
let mockAuthenticateRequest;
let mockInsert;

jest.mock('@google-cloud/functions-framework', () => ({
  http: jest.fn(),
}));

jest.mock('cors', () => () => (req, res, callback) => callback());

jest.mock('./auth', () => ({
  authenticateRequest: jest.fn((...args) => mockAuthenticateRequest(...args)),
}));

// Mock BigQuery: the insert function is captured via closure so we can
// reassign mockInsert per-test without losing the reference held by the module.
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

// Load the module under test — this registers 'telemetryIngestion' via
// functions.http().  We also import the helpers for direct unit-testing.
const {
  validateEvent,
  prepareRow,
  _resetBigQueryClient,
} = require('./telemetry');

// Grab the registered HTTP handler.
let telemetryHandler;

// ─── Helpers ────────────────────────────────────────────────────────────────

function makeReq(options = {}) {
  return {
    method: options.method || 'POST',
    headers: options.headers || { 'x-api-key': 'test-key' },
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
  // Spy on status and json so we can use expect().toHaveBeenCalled().
  jest.spyOn(res, 'status');
  jest.spyOn(res, 'json');
  return res;
}

function invokeHandler(req, res) {
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

    telemetryHandler(req, res);
  });
}

// ─── Setup ──────────────────────────────────────────────────────────────────

beforeAll(() => {
  // functions.http was called once when ./telemetry was required above.
  const calls = functions.http.mock.calls;
  const telemetryCalls = calls.filter((c) => c[0] === 'telemetryIngestion');
  expect(telemetryCalls.length).toBeGreaterThan(0);
  telemetryHandler = telemetryCalls[0][1];
});

beforeEach(() => {
  jest.clearAllMocks();
  // Default: auth succeeds.
  mockAuthenticateRequest = jest.fn().mockReturnValue({ clientId: 'test', authenticated: true });
  // Default: BigQuery insert succeeds.
  mockInsert = jest.fn().mockResolvedValue([]);
  // Reset cached BQ client so each test gets a fresh mock instance.
  _resetBigQueryClient();
});

// ─── validateEvent unit tests ────────────────────────────────────────────────

describe('validateEvent()', () => {
  const validEvent = {
    event_id: 'uuid-1',
    event_type: 'battery_status',
    source: 'ev3',
    timestamp: '2024-01-15T10:00:00.000Z',
    payload: { voltage_mv: 7200 },
  };

  test('accepts a fully-valid event', () => {
    const { valid, errors } = validateEvent(validEvent);
    expect(valid).toBe(true);
    expect(errors).toHaveLength(0);
  });

  test('accepts event with optional fields populated', () => {
    const { valid } = validateEvent({
      ...validEvent,
      device_id: 'ev3-001',
      session_id: 'sess-abc',
      version: '1.0.0',
      tags: ['production'],
      user_id: 'user-1',
      correlation_id: 'corr-1',
    });
    expect(valid).toBe(true);
  });

  test('rejects missing event_id', () => {
    const { valid, errors } = validateEvent({ ...validEvent, event_id: undefined });
    expect(valid).toBe(false);
    expect(errors.some((e) => e.includes('event_id'))).toBe(true);
  });

  test('rejects empty string event_id', () => {
    const { valid, errors } = validateEvent({ ...validEvent, event_id: '   ' });
    expect(valid).toBe(false);
    expect(errors.some((e) => e.includes('event_id'))).toBe(true);
  });

  test('rejects missing event_type', () => {
    const { valid, errors } = validateEvent({ ...validEvent, event_type: undefined });
    expect(valid).toBe(false);
    expect(errors.some((e) => e.includes('event_type'))).toBe(true);
  });

  test('rejects missing source', () => {
    const { valid, errors } = validateEvent({ ...validEvent, source: undefined });
    expect(valid).toBe(false);
    expect(errors.some((e) => e.includes('source'))).toBe(true);
  });

  test('rejects missing timestamp', () => {
    const { valid, errors } = validateEvent({ ...validEvent, timestamp: undefined });
    expect(valid).toBe(false);
    expect(errors.some((e) => e.includes('timestamp'))).toBe(true);
  });

  test('rejects invalid timestamp', () => {
    const { valid, errors } = validateEvent({ ...validEvent, timestamp: 'not-a-date' });
    expect(valid).toBe(false);
    expect(errors.some((e) => e.includes('timestamp'))).toBe(true);
  });

  test('rejects missing payload', () => {
    const { valid, errors } = validateEvent({ ...validEvent, payload: undefined });
    expect(valid).toBe(false);
    expect(errors.some((e) => e.includes('payload'))).toBe(true);
  });

  test('rejects null payload', () => {
    const { valid, errors } = validateEvent({ ...validEvent, payload: null });
    expect(valid).toBe(false);
    expect(errors.some((e) => e.includes('payload'))).toBe(true);
  });

  test('rejects array payload', () => {
    const { valid, errors } = validateEvent({ ...validEvent, payload: [1, 2, 3] });
    expect(valid).toBe(false);
    expect(errors.some((e) => e.includes('payload'))).toBe(true);
  });

  test('rejects non-array tags', () => {
    const { valid, errors } = validateEvent({ ...validEvent, tags: 'production' });
    expect(valid).toBe(false);
    expect(errors.some((e) => e.includes('tags'))).toBe(true);
  });

  test('accepts empty tags array', () => {
    const { valid } = validateEvent({ ...validEvent, tags: [] });
    expect(valid).toBe(true);
  });
});

// ─── prepareRow unit tests ───────────────────────────────────────────────────

describe('prepareRow()', () => {
  const event = {
    event_id: 'uuid-2',
    event_type: 'command_received',
    source: 'cloud_functions',
    timestamp: '2024-01-15T12:00:00.000Z',
    payload: { command: 'forward', speed: 500 },
    device_id: 'ev3-001',
    version: '1.0.0',
    tags: ['test'],
  };

  test('includes ingested_at timestamp', () => {
    const row = prepareRow(event);
    expect(row.ingested_at).toBeDefined();
    expect(new Date(row.ingested_at).getTime()).not.toBeNaN();
  });

  test('serialises payload to JSON string', () => {
    const row = prepareRow(event);
    expect(typeof row.payload).toBe('string');
    expect(JSON.parse(row.payload)).toEqual(event.payload);
  });

  test('preserves required fields verbatim', () => {
    const row = prepareRow(event);
    expect(row.event_id).toBe(event.event_id);
    expect(row.event_type).toBe(event.event_type);
    expect(row.source).toBe(event.source);
  });

  test('converts timestamp to ISO string', () => {
    const row = prepareRow(event);
    expect(row.timestamp).toBe(new Date(event.timestamp).toISOString());
  });

  test('sets optional absent fields to null', () => {
    const minimal = {
      event_id: 'e-1',
      event_type: 'test',
      source: 'ev3',
      timestamp: '2024-01-15T00:00:00Z',
      payload: {},
    };
    const row = prepareRow(minimal);
    expect(row.device_id).toBeNull();
    expect(row.session_id).toBeNull();
    expect(row.version).toBeNull();
    expect(row.tags).toBeNull();
    expect(row.user_id).toBeNull();
    expect(row.correlation_id).toBeNull();
  });
});

// ─── HTTP handler integration tests ─────────────────────────────────────────

describe('telemetryIngestion handler — HTTP method guard', () => {
  test('returns 405 for GET requests', async () => {
    const req = makeReq({ method: 'GET' });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(405);
  });

  test('returns 204 for OPTIONS (CORS preflight)', async () => {
    const req = makeReq({ method: 'OPTIONS' });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(204);
  });
});

describe('telemetryIngestion handler — authentication', () => {
  test('returns 401 when API key is missing', async () => {
    mockAuthenticateRequest = jest.fn().mockImplementation(() => {
      throw new Error('API key is required');
    });
    const req = makeReq({ headers: {} });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(401);
    expect(res.data.error).toBe('API key is required');
  });

  test('returns 401 for invalid API key', async () => {
    mockAuthenticateRequest = jest.fn().mockImplementation(() => {
      throw new Error('Invalid API key');
    });
    const req = makeReq({ headers: { 'x-api-key': 'wrong' } });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(401);
    expect(res.data.error).toBe('Invalid API key');
  });
});

describe('telemetryIngestion handler — request body validation', () => {
  test('returns 400 when events field is missing', async () => {
    const req = makeReq({ body: {} });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(400);
    expect(res.data.error).toMatch(/events/);
  });

  test('returns 400 when events is not an array', async () => {
    const req = makeReq({ body: { events: 'not-an-array' } });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(400);
    expect(res.data.error).toMatch(/array/);
  });

  test('returns 400 when events is an empty array', async () => {
    const req = makeReq({ body: { events: [] } });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(400);
    expect(res.data.error).toMatch(/empty/);
  });
});

// ─── Successful ingestion ────────────────────────────────────────────────────

describe('telemetryIngestion handler — successful ingestion', () => {
  const validEvent = {
    event_id: 'evt-001',
    event_type: 'battery_status',
    source: 'ev3',
    timestamp: '2024-01-15T10:00:00.000Z',
    payload: { voltage_mv: 7200, percentage: 85 },
    device_id: 'ev3-001',
    version: '1.0.0',
  };

  test('inserts a single valid event and returns 200', async () => {
    const req = makeReq({ body: { events: [validEvent] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.success).toBe(true);
    expect(res.data.inserted).toBe(1);
    expect(res.data.failed).toBe(0);
    expect(res.data.errors).toBeUndefined();
  });

  test('inserts multiple valid events and returns 200', async () => {
    const events = [
      validEvent,
      { ...validEvent, event_id: 'evt-002', event_type: 'command_received' },
      { ...validEvent, event_id: 'evt-003', event_type: 'error' },
    ];
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.success).toBe(true);
    expect(res.data.inserted).toBe(3);
    expect(res.data.failed).toBe(0);
    expect(mockInsert).toHaveBeenCalledTimes(1);
    expect(mockInsert.mock.calls[0][0]).toHaveLength(3);
  });

  test('BigQuery row includes ingested_at', async () => {
    const req = makeReq({ body: { events: [validEvent] } });
    const res = makeRes();
    await invokeHandler(req, res);

    const rows = mockInsert.mock.calls[0][0];
    expect(rows[0].ingested_at).toBeDefined();
    expect(new Date(rows[0].ingested_at).getTime()).not.toBeNaN();
  });

  test('BigQuery row payload is a JSON string', async () => {
    const req = makeReq({ body: { events: [validEvent] } });
    const res = makeRes();
    await invokeHandler(req, res);

    const rows = mockInsert.mock.calls[0][0];
    expect(typeof rows[0].payload).toBe('string');
    expect(JSON.parse(rows[0].payload)).toEqual(validEvent.payload);
  });
});

// ─── Validation failures (all events invalid) ────────────────────────────────

describe('telemetryIngestion handler — all events fail validation', () => {
  test('returns 400 with per-event error details when all events are invalid', async () => {
    const badEvents = [
      { event_id: 'x' }, // missing event_type, source, timestamp, payload
      { source: 'ev3' }, // missing event_id, event_type, timestamp, payload
    ];
    const req = makeReq({ body: { events: badEvents } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(400);
    expect(res.data.success).toBe(false);
    expect(res.data.inserted).toBe(0);
    expect(res.data.failed).toBe(2);
    expect(res.data.errors).toHaveLength(2);
    // BigQuery should not be called when all events fail validation.
    expect(mockInsert).not.toHaveBeenCalled();
  });
});

// ─── Mixed valid + invalid events ────────────────────────────────────────────

describe('telemetryIngestion handler — mixed valid and invalid events', () => {
  const validEvent = {
    event_id: 'evt-good',
    event_type: 'battery_status',
    source: 'ev3',
    timestamp: '2024-01-15T10:00:00.000Z',
    payload: { voltage_mv: 7200 },
  };

  test('inserts valid events, reports invalid ones, returns 207', async () => {
    const events = [
      validEvent,
      { event_id: 'evt-bad' }, // missing required fields
    ];
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(207);
    expect(res.data.success).toBe(false);
    expect(res.data.inserted).toBe(1);
    expect(res.data.failed).toBe(1);
    expect(res.data.errors).toHaveLength(1);
    expect(res.data.errors[0].event_id).toBe('evt-bad');
    expect(mockInsert).toHaveBeenCalledTimes(1);
    expect(mockInsert.mock.calls[0][0]).toHaveLength(1);
  });
});

// ─── BigQuery errors ─────────────────────────────────────────────────────────

describe('telemetryIngestion handler — BigQuery errors', () => {
  const validEvent = {
    event_id: 'evt-bq',
    event_type: 'command_executed',
    source: 'cloud_functions',
    timestamp: '2024-01-15T10:00:00.000Z',
    payload: { command: 'stop' },
  };

  test('returns 500 on unexpected BigQuery error', async () => {
    mockInsert = jest.fn().mockRejectedValue(new Error('Connection refused'));
    const req = makeReq({ body: { events: [validEvent] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(500);
    expect(res.data.success).toBe(false);
    expect(res.data.error).toMatch(/BigQuery/i);
  });

  test('returns 207 on BigQuery PartialFailureError', async () => {
    const partialError = new Error('PartialFailureError');
    partialError.name = 'PartialFailureError';
    partialError.errors = [
      {
        row: { event_id: 'evt-bq', event_type: 'command_executed' },
        errors: [{ reason: 'invalid', message: 'Required field missing', location: 'payload' }],
      },
    ];
    mockInsert = jest.fn().mockRejectedValue(partialError);

    const events = [
      validEvent,
      { ...validEvent, event_id: 'evt-bq2', event_type: 'battery_status' },
    ];
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(207);
    expect(res.data.success).toBe(false);
    expect(res.data.inserted).toBe(1); // one of two rows failed
    expect(res.data.failed).toBe(1);
    expect(res.data.errors[0].event_id).toBe('evt-bq');
    expect(res.data.errors[0].errors[0]).toMatch(/Required field missing/);
  });
});
