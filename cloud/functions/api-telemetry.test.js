'use strict';

/**
 * Unit tests for api-telemetry.js
 *
 * Covers:
 * - sanitizeParams: speak text redaction, passthrough of numeric params
 * - buildApiRequestEvent: correct envelope shape and payload fields
 * - logApiRequest: fire-and-forget (non-blocking), BigQuery errors swallowed
 */

let mockInsert;
let mockTable;
let mockDataset;
let mockBqInstance;

jest.mock('@google-cloud/bigquery', () => {
  const BigQuery = jest.fn(() => mockBqInstance);
  return { BigQuery };
});

const { BigQuery } = require('@google-cloud/bigquery');

const {
  sanitizeParams,
  buildApiRequestEvent,
  logApiRequest,
  _resetBqClient,
} = require('./api-telemetry');

beforeEach(async () => {
  // Drain any setImmediate callbacks queued by the previous test before
  // resetting mocks, so stale callbacks don't inflate call counts.
  await new Promise((resolve) => setImmediate(resolve));

  jest.clearAllMocks();
  _resetBqClient();

  mockInsert = jest.fn().mockResolvedValue(undefined);
  mockTable = { insert: mockInsert };
  mockDataset = { table: jest.fn(() => mockTable) };
  mockBqInstance = { dataset: jest.fn(() => mockDataset) };
});

// ---------------------------------------------------------------------------
// sanitizeParams
// ---------------------------------------------------------------------------

describe('sanitizeParams', () => {
  test('returns null for null params', () => {
    expect(sanitizeParams('forward', null)).toBeNull();
  });

  test('returns null for undefined params', () => {
    expect(sanitizeParams('forward', undefined)).toBeNull();
  });

  test('returns null for non-object params', () => {
    expect(sanitizeParams('forward', 'invalid')).toBeNull();
    expect(sanitizeParams('forward', 42)).toBeNull();
    expect(sanitizeParams('forward', [])).toBeNull();
  });

  test('passes numeric params through unchanged for movement commands', () => {
    const params = { speed: 500, duration: 2 };
    expect(sanitizeParams('forward', params)).toEqual({ speed: 500, duration: 2 });
  });

  test('passes joystick params through unchanged', () => {
    const params = { l_left: 0.5, l_forward: 0.8, r_left: 0, r_forward: 0 };
    expect(sanitizeParams('joystick_control', params)).toEqual(params);
  });

  test('replaces speak text with length placeholder', () => {
    const params = { text: 'Hello robot!' };
    const result = sanitizeParams('speak', params);
    expect(result).toEqual({ text: '[12 chars]' });
    expect(result.text).not.toContain('Hello');
  });

  test('handles empty speak text', () => {
    const result = sanitizeParams('speak', { text: '' });
    expect(result).toEqual({ text: '[0 chars]' });
  });

  test('does not mutate the original params object', () => {
    const params = { text: 'secret message' };
    sanitizeParams('speak', params);
    expect(params.text).toBe('secret message');
  });

  test('leaves non-text speak params unchanged', () => {
    const params = { text: 'Hi', volume: 80 };
    const result = sanitizeParams('speak', params);
    expect(result.volume).toBe(80);
    expect(result.text).toBe('[2 chars]');
  });

  test('passes beep params through unchanged', () => {
    const params = { frequency: 440, duration: 0.5 };
    expect(sanitizeParams('beep', params)).toEqual(params);
  });
});

// ---------------------------------------------------------------------------
// buildApiRequestEvent
// ---------------------------------------------------------------------------

describe('buildApiRequestEvent', () => {
  const baseData = {
    method: 'POST',
    command: 'forward',
    params: { speed: 500 },
    statusCode: 200,
    totalLatencyMs: 150,
    robotLatencyMs: 80,
    clientIpHash: 'abc123hash',
    errorMessage: null,
  };

  test('produces a valid event envelope', () => {
    const event = buildApiRequestEvent(baseData);

    expect(event.event_type).toBe('api_request');
    expect(event.source).toBe('cloud_functions');
    expect(typeof event.event_id).toBe('string');
    expect(event.event_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
    );
    expect(typeof event.timestamp).toBe('string');
    expect(new Date(event.timestamp).getTime()).not.toBeNaN();
  });

  test('sets correct payload fields', () => {
    const event = buildApiRequestEvent(baseData);
    const { payload } = event;

    expect(payload.endpoint).toBe('controlRobot');
    expect(payload.method).toBe('POST');
    expect(payload.command).toBe('forward');
    expect(payload.status_code).toBe(200);
    expect(payload.latency_ms).toBe(150);
    expect(payload.robot_response_time_ms).toBe(80);
    expect(payload.client_ip_hash).toBe('abc123hash');
    expect(payload.error_message).toBeNull();
  });

  test('sanitizes speak params in payload', () => {
    const event = buildApiRequestEvent({
      ...baseData,
      command: 'speak',
      params: { text: 'Hello world' },
    });
    expect(event.payload.sanitized_params).toEqual({ text: '[11 chars]' });
  });

  test('passes numeric params through to sanitized_params', () => {
    const event = buildApiRequestEvent(baseData);
    expect(event.payload.sanitized_params).toEqual({ speed: 500 });
  });

  test('sets sanitized_params to null when params is null', () => {
    const event = buildApiRequestEvent({ ...baseData, params: null });
    expect(event.payload.sanitized_params).toBeNull();
  });

  test('sets robot_response_time_ms to null when robotLatencyMs is null', () => {
    const event = buildApiRequestEvent({ ...baseData, robotLatencyMs: null });
    expect(event.payload.robot_response_time_ms).toBeNull();
  });

  test('sets command to null when command is null', () => {
    const event = buildApiRequestEvent({ ...baseData, command: null });
    expect(event.payload.command).toBeNull();
  });

  test('includes error_message when provided', () => {
    const event = buildApiRequestEvent({ ...baseData, errorMessage: 'Connection timeout' });
    expect(event.payload.error_message).toBe('Connection timeout');
  });

  test('generates unique event_ids', () => {
    const e1 = buildApiRequestEvent(baseData);
    const e2 = buildApiRequestEvent(baseData);
    expect(e1.event_id).not.toBe(e2.event_id);
  });

  test('sets client_ip_hash to null when not provided', () => {
    const event = buildApiRequestEvent({ ...baseData, clientIpHash: null });
    expect(event.payload.client_ip_hash).toBeNull();
  });

  test('records the actual HTTP method in payload.method', () => {
    const event = buildApiRequestEvent({ ...baseData, method: 'GET' });
    expect(event.payload.method).toBe('GET');
  });

  test('defaults method to POST when not provided', () => {
    const { method: _m, ...dataWithoutMethod } = baseData;
    const event = buildApiRequestEvent(dataWithoutMethod);
    expect(event.payload.method).toBe('POST');
  });
});

// ---------------------------------------------------------------------------
// logApiRequest — fire-and-forget behaviour
// ---------------------------------------------------------------------------

describe('logApiRequest', () => {
  const baseData = {
    method: 'POST',
    command: 'stop',
    params: {},
    statusCode: 200,
    totalLatencyMs: 50,
    robotLatencyMs: 20,
    clientIpHash: 'hash123',
    errorMessage: null,
  };

  test('returns synchronously without awaiting BigQuery', () => {
    // If logApiRequest were async/blocking, this would hang.
    const start = Date.now();
    logApiRequest(baseData);
    const elapsed = Date.now() - start;
    // Should complete in well under 50 ms synchronously.
    expect(elapsed).toBeLessThan(50);
  });

  test('does not call BigQuery insert before setImmediate fires', () => {
    logApiRequest(baseData);
    // setImmediate hasn't fired yet — BigQuery should not have been called.
    expect(mockInsert).not.toHaveBeenCalled();
  });

  test('calls BigQuery insert after setImmediate fires', async () => {
    logApiRequest(baseData);
    // Flush the event loop to allow setImmediate callback to run.
    await new Promise((resolve) => setImmediate(resolve));
    expect(mockInsert).toHaveBeenCalledTimes(1);
  });

  test('inserts a row with correct event_type and source', async () => {
    logApiRequest(baseData);
    await new Promise((resolve) => setImmediate(resolve));

    const [rows] = mockInsert.mock.calls[0];
    expect(rows).toHaveLength(1);
    const row = rows[0];
    expect(row.event_type).toBe('api_request');
    expect(row.source).toBe('cloud_functions');
    expect(typeof row.event_id).toBe('string');
    expect(typeof row.payload).toBe('string'); // BigQuery JSON column
  });

  test('payload JSON contains expected fields', async () => {
    logApiRequest(baseData);
    await new Promise((resolve) => setImmediate(resolve));

    const [rows] = mockInsert.mock.calls[0];
    const payload = JSON.parse(rows[0].payload);
    expect(payload.endpoint).toBe('controlRobot');
    expect(payload.status_code).toBe(200);
    expect(payload.latency_ms).toBe(50);
    expect(payload.robot_response_time_ms).toBe(20);
  });

  test('records non-POST method in BigQuery payload', async () => {
    logApiRequest({ ...baseData, method: 'DELETE' });
    await new Promise((resolve) => setImmediate(resolve));

    const [rows] = mockInsert.mock.calls[0];
    const payload = JSON.parse(rows[0].payload);
    expect(payload.method).toBe('DELETE');
  });

  test('swallows BigQuery insert errors without throwing', async () => {
    mockInsert.mockRejectedValue(new Error('BigQuery unavailable'));

    // Should not throw or cause unhandled rejection.
    logApiRequest(baseData);
    await new Promise((resolve) => setImmediate(resolve));
    // Give the rejection handler a tick to run.
    await Promise.resolve();

    // If we reach here without an unhandled rejection, the test passes.
    expect(mockInsert).toHaveBeenCalledTimes(1);
  });

  test('logging errors do not affect a concurrent caller', async () => {
    // Simulate a slow BigQuery insert that would block if awaited.
    let resolveInsert;
    mockInsert.mockReturnValue(new Promise((r) => { resolveInsert = r; }));

    const start = Date.now();
    logApiRequest(baseData);
    // The call must complete synchronously; don't wait for the BQ insert.
    const elapsed = Date.now() - start;
    expect(elapsed).toBeLessThan(50);

    // Clean up: resolve the pending insert so Jest doesn't complain about it.
    resolveInsert();
    await new Promise((resolve) => setImmediate(resolve));
  });

  test('handles build errors gracefully (e.g. null data)', async () => {
    // Passing null should not throw; the error is caught internally.
    expect(() => logApiRequest(null)).not.toThrow();
    await new Promise((resolve) => setImmediate(resolve));
    // BigQuery should not have been called because the build failed.
    expect(mockInsert).not.toHaveBeenCalled();
  });
});
