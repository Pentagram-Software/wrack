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
  isValidTypeField,
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

// ─── isValidTypeField() unit tests ───────────────────────────────────────────

describe('isValidTypeField()', () => {
  test('true when type is absent', () => {
    expect(isValidTypeField({})).toBe(true);
  });

  test('true when type is explicitly null', () => {
    expect(isValidTypeField({ type: null })).toBe(true);
  });

  test('true for "health" and "event"', () => {
    expect(isValidTypeField({ type: 'health' })).toBe(true);
    expect(isValidTypeField({ type: 'event' })).toBe(true);
  });

  test('false for an unrecognized value', () => {
    expect(isValidTypeField({ type: 'bogus' })).toBe(false);
  });

  test('false for a typo close to a valid value', () => {
    expect(isValidTypeField({ type: 'Health' })).toBe(false);
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

  test('rejects a device_id that names an inherited Object.prototype property (prototype-chain bypass)', async () => {
    const req = makeReq({
      headers: { 'x-device-id': 'toString', 'x-device-token': String(Object.prototype.toString) },
    });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(401);
    expect(res.data.error).toMatch(/Invalid device credentials/);
  });

  test('rejects "constructor" as a device_id the same way', async () => {
    const req = makeReq({
      headers: { 'x-device-id': 'constructor', 'x-device-token': String(Object.prototype.constructor) },
    });
    const res = makeRes();
    await invokeHandler(req, res);
    expect(res.statusCode).toBe(401);
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

  test('re-fetches the secret once the cache TTL has elapsed, picking up a rotated token', async () => {
    const nowSpy = jest.spyOn(Date, 'now');
    nowSpy.mockReturnValue(1_000_000);

    const req1 = makeReq({ body: { events: [validEvent({ event_id: 'e1' })] } });
    await invokeHandler(req1, makeRes());
    expect(mockAccessSecretVersion).toHaveBeenCalledTimes(1);

    // Simulate a rotation: the secret now returns a different token for ev3-001.
    mockAccessSecretVersion = jest.fn().mockResolvedValue([
      { payload: { data: Buffer.from(JSON.stringify({ ...DEVICE_TOKENS, 'ev3-001': 'ev3-rotated-token' })) } },
    ]);

    // Still within the TTL — old cached token should still be accepted, new
    // one not yet known.
    nowSpy.mockReturnValue(1_000_000 + 60 * 1000);
    const req2 = makeReq({ body: { events: [validEvent({ event_id: 'e2' })] } });
    const res2 = makeRes();
    await invokeHandler(req2, res2);
    expect(res2.statusCode).toBe(200);
    expect(mockAccessSecretVersion).toHaveBeenCalledTimes(0);

    // Past the TTL — should re-fetch, and the old token must now be rejected.
    nowSpy.mockReturnValue(1_000_000 + 6 * 60 * 1000);
    const req3 = makeReq({ body: { events: [validEvent({ event_id: 'e3' })] } });
    const res3 = makeRes();
    await invokeHandler(req3, res3);
    expect(res3.statusCode).toBe(401);

    const req4 = makeReq({
      headers: { 'x-device-id': 'ev3-001', 'x-device-token': 'ev3-rotated-token' },
      body: { events: [validEvent({ event_id: 'e4' })] },
    });
    const res4 = makeRes();
    await invokeHandler(req4, res4);
    expect(res4.statusCode).toBe(200);
    expect(mockAccessSecretVersion).toHaveBeenCalledTimes(1);

    nowSpy.mockRestore();
  });
});

// ─── Device identity binding ──────────────────────────────────────────────────

describe('unifiedIngress handler — device identity binding', () => {
  test('overwrites a spoofed device_id with the authenticated device identity before insert', async () => {
    const event = validEvent({ device_id: 'rpi-camera-01' }); // ev3-001's token, claiming to be the Pi
    const req = makeReq({ body: { events: [event] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    const insertedRows = mockInsert.mock.calls[0][0];
    expect(insertedRows[0].json.device_id).toBe('ev3-001');
  });

  test('stamps the authenticated device identity even when device_id is absent from the payload', async () => {
    const event = validEvent();
    delete event.device_id;
    const req = makeReq({ body: { events: [event] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    const insertedRows = mockInsert.mock.calls[0][0];
    expect(insertedRows[0].json.device_id).toBe('ev3-001');
  });

  test('stamps the authenticated device identity on health records too', async () => {
    process.env.HEALTH_LEG_FUNCTION_URL = 'https://example.test/health-leg';
    const event = validEvent({
      type: 'health',
      event_type: 'device_status',
      payload: { device_name: 'ev3', status: 'connected' },
      device_id: 'rpi-camera-01',
    });
    const req = makeReq({ body: { events: [event] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    const pushedBody = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(pushedBody.device_id).toBe('ev3-001');
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

  test('BigQuery partial-failure errors omit index, so the sender classifies them as retryable', async () => {
    // sender.py::_classify_207 treats any error entry carrying an `index` as
    // a permanent validation failure, and any entry with only `event_id` as
    // a retryable BigQuery failure — the exact contract telemetry.js already
    // established. Regressing this (e.g. by adding `index` back) silently
    // turns transient BigQuery errors into dropped, never-retried events.
    const partialError = new Error('PartialFailureError');
    partialError.name = 'PartialFailureError';
    partialError.errors = [
      {
        row: { insertId: 'evt-bad', json: { event_id: 'evt-bad' } },
        errors: [{ reason: 'backendError', message: 'transient BigQuery error' }],
      },
    ];
    mockInsert = jest.fn().mockRejectedValue(partialError);

    const events = [validEvent({ event_id: 'evt-good' }), validEvent({ event_id: 'evt-bad' })];
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(207);
    expect(res.data.errors[0]).toEqual({ event_id: 'evt-bad', errors: expect.any(Array) });
    expect('index' in res.data.errors[0]).toBe(false);
  });

  test('a hard BigQuery failure also omits index, when surfaced alongside a successful health record', async () => {
    // A fully-hard-failed batch on its own returns a 500 with a single
    // top-level error, not a per-event array — mixing in a health record
    // (which always "succeeds" from the caller's point of view) forces the
    // 207 path instead, so the per-event error shape is actually observable.
    process.env.HEALTH_LEG_FUNCTION_URL = 'https://example.test/health-leg';
    mockInsert = jest.fn().mockRejectedValue(new Error('Connection refused'));
    const events = [
      validEvent({ event_id: 'evt-a' }),
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
    expect(res.data.errors[0]).toEqual({ event_id: 'evt-a', errors: ['Connection refused'] });
    expect('index' in res.data.errors[0]).toBe(false);
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

  test('passes an abort signal so a stalled health endpoint cannot hang the request', async () => {
    process.env.HEALTH_LEG_FUNCTION_URL = 'https://example.test/health-leg';
    const event = validEvent({ type: 'health', event_type: 'device_status', payload: { device_name: 'ev3', status: 'connected' } });
    const req = makeReq({ body: { events: [event] } });
    await invokeHandler(req, makeRes());

    const fetchOptions = global.fetch.mock.calls[0][1];
    expect(fetchOptions.signal).toBeInstanceOf(AbortSignal);
  });

  test('fails open (still counted inserted) when the health-leg call times out', async () => {
    process.env.HEALTH_LEG_FUNCTION_URL = 'https://example.test/health-leg';
    global.fetch = jest.fn().mockRejectedValue(new DOMException('The operation was aborted due to timeout', 'TimeoutError'));
    const event = validEvent({ type: 'health', event_type: 'device_status', payload: { device_name: 'ev3', status: 'connected' } });
    const req = makeReq({ body: { events: [event] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.inserted).toBe(1);
    expect(res.data.failed).toBe(0);
  });

  test('caps concurrent health-leg pushes so a large batch cannot open unbounded outbound connections', async () => {
    process.env.HEALTH_LEG_FUNCTION_URL = 'https://example.test/health-leg';

    let inFlight = 0;
    let maxInFlight = 0;
    global.fetch = jest.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          inFlight += 1;
          maxInFlight = Math.max(maxInFlight, inFlight);
          setTimeout(() => {
            inFlight -= 1;
            resolve({ ok: true, status: 200 });
          }, 0);
        })
    );

    const events = Array.from({ length: 45 }, (_, i) =>
      validEvent({
        event_id: `evt-health-${i}`,
        type: 'health',
        event_type: 'device_status',
        payload: { device_name: 'ev3', status: 'connected' },
      })
    );
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    expect(res.data.inserted).toBe(45);
    expect(global.fetch).toHaveBeenCalledTimes(45);
    expect(maxInFlight).toBeLessThanOrEqual(20);
  });

  test('stops attempting further health chunks once the total time budget is exceeded', async () => {
    // Chunking bounds concurrency but chunks run sequentially — if every
    // chunk took close to its full per-item timeout, a large batch could
    // blow well past the senders' own HTTP timeout. Simulates that by
    // advancing a mocked Date.now() on every call (independent of real
    // elapsed time, so the test runs instantly) until the budget trips.
    process.env.HEALTH_LEG_FUNCTION_URL = 'https://example.test/health-leg';

    const nowSpy = jest.spyOn(Date, 'now');
    let calls = 0;
    const base = 1_000_000;
    nowSpy.mockImplementation(() => base + calls++ * 2500);

    const events = Array.from({ length: 100 }, (_, i) =>
      validEvent({
        event_id: `evt-health-${i}`,
        type: 'health',
        event_type: 'device_status',
        payload: { device_name: 'ev3', status: 'connected' },
      })
    );
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(200);
    // Every health record still counts as inserted (fail open) even though
    // most were never attempted — same policy as any other health failure.
    expect(res.data.inserted).toBe(100);
    // Only the first chunk (20 records) should have been attempted before
    // the second deadline check reports the budget exceeded.
    expect(global.fetch).toHaveBeenCalledTimes(20);

    nowSpy.mockRestore();
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

  test('rejects an event with an unrecognized type value instead of routing it to BigQuery', async () => {
    const event = validEvent({ type: 'bogus' });
    const req = makeReq({ body: { events: [event] } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(400);
    expect(res.data.success).toBe(false);
    expect(res.data.errors[0].errors.some((e) => e.includes('type'))).toBe(true);
    expect(mockInsert).not.toHaveBeenCalled();
  });

  test('rejects an event with a typo type value in a mixed batch, without misrouting it', async () => {
    const events = [validEvent({ event_id: 'evt-good' }), validEvent({ event_id: 'evt-typo', type: 'Health' })];
    const req = makeReq({ body: { events } });
    const res = makeRes();
    await invokeHandler(req, res);

    expect(res.statusCode).toBe(207);
    expect(res.data.inserted).toBe(1);
    expect(res.data.failed).toBe(1);
    expect(res.data.errors[0].event_id).toBe('evt-typo');
    expect(mockInsert.mock.calls[0][0]).toHaveLength(1);
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
