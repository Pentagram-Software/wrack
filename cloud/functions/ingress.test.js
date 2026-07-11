'use strict';

/**
 * Unit tests for the unifiedIngress Cloud Function (PEN-227).
 *
 * Strategy mirrors telemetry.test.js:
 *  - Mock @google-cloud/functions-framework so registrations are captured.
 *  - Mock cors to invoke callback synchronously.
 *  - Mock @google-cloud/secret-manager so device-token lookups are controllable.
 *  - Mock @google-cloud/bigquery via a variable-captured insert function.
 *  - Mock global.fetch for the health-leg push.
 */

// --- Module-level mock variables (reassigned in beforeEach) ---
let mockAccessSecretVersion;
let mockInsert;

jest.mock('@google-cloud/functions-framework', () => ({
  http: jest.fn(),
}));

jest.mock('cors', () => () => (req, res, callback) => callback());

jest.mock('@google-cloud/secret-manager', () => ({
  SecretManagerServiceClient: jest.fn().mockImplementation(() => ({
    accessSecretVersion: (...args) => mockAccessSecretVersion(...args),
  })),
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
const { _resetClient: _resetBigQueryClient, _setSleepFn } = require('./bigquery-client');

const DEVICE_TOKENS = {
  'ev3-001': 'ev3-good-token',
  'rpi-camera-01': 'rpi-good-token',
};

// Load the module under test — this registers 'unifiedIngress' via
// functions.http(). We also import the helpers for direct unit-testing.
const {
  resolveType,
  _timingSafeStringEqual,
  _resetDeviceTokensCache,
} = require('./ingress');

let ingressHandler;

// ─── Helpers ────────────────────────────────────────────────────────────────

function makeReq(options = {}) {
  return {
    method: options.method || 'POST',
    headers: options.headers || {
      'x-device-id': 'ev3-001',
      'x-device-token': 'ev3-good-token',
    },
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

    ingressHandler(req, res);
  });
}

function validEvent(overrides = {}) {
  return {
    event_id: 'evt-001',
    event_type: 'battery_status',
    source: 'ev3',
    timestamp: '2024-01-15T10:00:00.000Z',
    payload: { voltage_mv: 7200, percentage: 85 },
    device_id: 'ev3-001',
    ...overrides,
  };
}

// ─── Setup ──────────────────────────────────────────────────────────────────

beforeAll(() => {
  const calls = functions.http.mock.calls;
  const ingressCalls = calls.filter((c) => c[0] === 'unifiedIngress');
  expect(ingressCalls.length).toBeGreaterThan(0);
  ingressHandler = ingressCalls[0][1];
});

beforeEach(() => {
  jest.clearAllMocks();
  _resetDeviceTokensCache();
  _resetBigQueryClient();
  _setSleepFn(() => Promise.resolve()); // retries complete instantly in tests

  mockAccessSecretVersion = jest.fn().mockResolvedValue([
    { payload: { data: Buffer.from(JSON.stringify(DEVICE_TOKENS)) } },
  ]);
  mockInsert = jest.fn().mockResolvedValue([]);

  process.env.BIGQUERY_PROJECT_ID = 'test-project';
  delete process.env.HEALTH_LEG_FUNCTION_URL;

  global.fetch = jest.fn().mockResolvedValue({ ok: true, status: 200 });
});

afterEach(() => {
  delete process.env.BIGQUERY_PROJECT_ID;
  delete process.env.HEALTH_LEG_FUNCTION_URL;
});

// ─── resolveType() unit tests ────────────────────────────────────────────────

describe('resolveType()', () => {
  test('returns "health" when type is explicitly "health"', () => {
    expect(resolveType({ type: 'health' })).toBe('health');
  });

  test('defaults to "event" when type is absent', () => {
    expect(resolveType({})).toBe('event');
  });

  test('defaults to "event" for an unrecognized type value', () => {
    expect(resolveType({ type: 'bogus' })).toBe('event');
  });

  test('defaults to "event" when type is explicitly "event"', () => {
    expect(resolveType({ type: 'event' })).toBe('event');
  });
});

// ─── _timingSafeStringEqual() unit tests ─────────────────────────────────────

describe('_timingSafeStringEqual()', () => {
  test('returns true for equal strings', () => {
    expect(_timingSafeStringEqual('abc123', 'abc123')).toBe(true);
  });

  test('returns false for different strings of equal length', () => {
    expect(_timingSafeStringEqual('abc123', 'abc124')).toBe(false);
  });

  test('returns false for strings of different length (no throw)', () => {
    expect(_timingSafeStringEqual('short', 'a-much-longer-string')).toBe(false);
  });
});

// ─── HTTP method guard ────────────────────────────────────────────────────────

describe('unifiedIngress handler — HTTP method guard', () => {
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

// ─── Per-device authentication ────────────────────────────────────────────────

describe('unifiedIngress handler — per-device authentication', () => {
  test('returns 401 when X-Device-Id is missing', async () => {
    const req = makeReq({ headers: { 'x-device-token': 'ev3-good-token' } });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(401);
    expect(res.data.error).toMatch(/X-Device-Id/);
  });

  test('returns 401 when X-Device-Token is missing', async () => {
    const req = makeReq({ headers: { 'x-device-id': 'ev3-001' } });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(401);
  });

  test('returns 401 for an unknown device_id', async () => {
    const req = makeReq({ headers: { 'x-device-id': 'unknown-device', 'x-device-token': 'whatever' } });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(401);
    expect(res.data.error).toMatch(/Invalid device credentials/);
  });

  test('returns 401 for a known device_id with the wrong token', async () => {
    const req = makeReq({ headers: { 'x-device-id': 'ev3-001', 'x-device-token': 'wrong-token' } });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(401);
    expect(res.data.error).toMatch(/Invalid device credentials/);
  });

  test('accepts a known device_id with the matching token', async () => {
    const req = makeReq({ body: { events: [validEvent()] } });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(200);
  });

  test('a second request in the same warm instance does not re-fetch the secret', async () => {
    const req1 = makeReq({ body: { events: [validEvent({ event_id: 'e1' })] } });
    await invokeHandler(req1, makeRes());
    const req2 = makeReq({ body: { events: [validEvent({ event_id: 'e2' })] } });
    await invokeHandler(req2, makeRes());
    expect(mockAccessSecretVersion).toHaveBeenCalledTimes(1);
  });
});

// ─── Request body validation ──────────────────────────────────────────────────

describe('unifiedIngress handler — request body validation', () => {
  test('returns 400 when events field is missing', async () => {
    const req = makeReq({ body: {} });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(400);
  });

  test('returns 400 when events is not an array', async () => {
    const req = makeReq({ body: { events: 'nope' } });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(400);
  });

  test('returns 400 when events is an empty array', async () => {
    const req = makeReq({ body: { events: [] } });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(400);
  });
});

// ─── type=event routing (default) ─────────────────────────────────────────────

describe('unifiedIngress handler — type=event routing', () => {
  test('an event with no type field is inserted into BigQuery (default to event)', async () => {
    const req = makeReq({ body: { events: [validEvent()] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.inserted).toBe(1);
    expect(mockInsert).toHaveBeenCalledTimes(1);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('an event with type: "event" is inserted into BigQuery', async () => {
    const req = makeReq({ body: { events: [validEvent({ type: 'event' })] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    expect(mockInsert).toHaveBeenCalledTimes(1);
  });

  test('returns 500 when BigQuery insert fails hard and nothing else in the batch succeeded', async () => {
    mockInsert = jest.fn().mockRejectedValue(new Error('Connection refused'));
    const req = makeReq({ body: { events: [validEvent()] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(500);
    expect(res.data.success).toBe(false);
  });

  test('returns 207 on BigQuery PartialFailureError with correct inserted/failed split', async () => {
    const partialError = new Error('PartialFailureError');
    partialError.name = 'PartialFailureError';
    partialError.errors = [
      {
        row: { insertId: 'evt-bad', json: { event_id: 'evt-bad' } },
        errors: [{ reason: 'invalid', message: 'Bad row' }],
      },
    ];
    mockInsert = jest.fn().mockRejectedValue(partialError);

    const events = [validEvent({ event_id: 'evt-good' }), validEvent({ event_id: 'evt-bad' })];
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(207);
    expect(res.data.inserted).toBe(1);
    expect(res.data.failed).toBe(1);
    expect(res.data.errors[0].event_id).toBe('evt-bad');
  });
});

// ─── type=health routing ──────────────────────────────────────────────────────

describe('unifiedIngress handler — type=health routing', () => {
  test('a health event is POSTed to HEALTH_LEG_FUNCTION_URL, not inserted into BigQuery', async () => {
    process.env.HEALTH_LEG_FUNCTION_URL = 'https://example.test/health-leg';
    const event = validEvent({ type: 'health', event_type: 'device_status', payload: { device_name: 'ev3', status: 'connected' } });
    const req = makeReq({ body: { events: [event] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.inserted).toBe(1);
    expect(mockInsert).not.toHaveBeenCalled();
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch.mock.calls[0][0]).toBe('https://example.test/health-leg');
    const body = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(body.event_id).toBe(event.event_id);
  });

  test('fails open (still counted inserted) when HEALTH_LEG_FUNCTION_URL is unset', async () => {
    const event = validEvent({ type: 'health', event_type: 'device_status', payload: { device_name: 'ev3', status: 'connected' } });
    const req = makeReq({ body: { events: [event] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.inserted).toBe(1);
    expect(res.data.failed).toBe(0);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('fails open (still counted inserted) when the health-leg call errors', async () => {
    process.env.HEALTH_LEG_FUNCTION_URL = 'https://example.test/health-leg';
    global.fetch = jest.fn().mockRejectedValue(new Error('network down'));
    const event = validEvent({ type: 'health', event_type: 'device_status', payload: { device_name: 'ev3', status: 'connected' } });
    const req = makeReq({ body: { events: [event] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.inserted).toBe(1);
    expect(res.data.failed).toBe(0);
  });

  test('fails open (still counted inserted) when the health-leg call responds non-2xx', async () => {
    process.env.HEALTH_LEG_FUNCTION_URL = 'https://example.test/health-leg';
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 503 });
    const event = validEvent({ type: 'health', event_type: 'device_status', payload: { device_name: 'ev3', status: 'connected' } });
    const req = makeReq({ body: { events: [event] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.inserted).toBe(1);
    expect(res.data.failed).toBe(0);
  });
});

// ─── Mixed batches ─────────────────────────────────────────────────────────────

describe('unifiedIngress handler — mixed type=event and type=health batch', () => {
  test('routes each record correctly and combines counts', async () => {
    process.env.HEALTH_LEG_FUNCTION_URL = 'https://example.test/health-leg';
    const events = [
      validEvent({ event_id: 'evt-analytics' }),
      validEvent({
        event_id: 'evt-health',
        type: 'health',
        event_type: 'device_status',
        payload: { device_name: 'ev3', status: 'connected' },
      }),
    ];
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.inserted).toBe(2);
    expect(mockInsert).toHaveBeenCalledTimes(1);
    expect(mockInsert.mock.calls[0][0]).toHaveLength(1); // only the analytics event
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  test('a BigQuery hard failure only fails the event rows, health rows still succeed', async () => {
    process.env.HEALTH_LEG_FUNCTION_URL = 'https://example.test/health-leg';
    mockInsert = jest.fn().mockRejectedValue(new Error('Connection refused'));
    const events = [
      validEvent({ event_id: 'evt-analytics' }),
      validEvent({
        event_id: 'evt-health',
        type: 'health',
        event_type: 'device_status',
        payload: { device_name: 'ev3', status: 'connected' },
      }),
    ];
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(207);
    expect(res.data.inserted).toBe(1); // the health record
    expect(res.data.failed).toBe(1); // the analytics event
    expect(res.data.errors[0].event_id).toBe('evt-analytics');
  });
});

// ─── Validation failures ────────────────────────────────────────────────────────

describe('unifiedIngress handler — validation failures', () => {
  test('returns 400 with per-event error details when all events are invalid', async () => {
    const req = makeReq({ body: { events: [{ event_id: 'x' }] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(400);
    expect(res.data.success).toBe(false);
    expect(mockInsert).not.toHaveBeenCalled();
  });

  test('returns 207 for a mix of valid and invalid events', async () => {
    const events = [validEvent(), { event_id: 'bad-one' }];
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(207);
    expect(res.data.inserted).toBe(1);
    expect(res.data.failed).toBe(1);
  });
});
