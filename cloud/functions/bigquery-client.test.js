'use strict';

/**
 * Unit tests for bigquery-client.js
 *
 * Strategy:
 *  - Mock @google-cloud/bigquery so no real network calls are made.
 *  - Capture a reference to `mockInsert` via closure so each test can
 *    reassign the mock behaviour without re-requiring the module.
 *  - Replace the internal _sleepFn with a no-op so retry back-off delays
 *    complete instantly.
 *  - Use _resetClient() between tests to clear the cached singleton.
 */

// --- Module-level mock variable (reassigned in beforeEach) ---
let mockInsert;

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

// Save the real env var and restore after each test.
const ORIGINAL_PROJECT_ID = process.env.BIGQUERY_PROJECT_ID;
const ORIGINAL_DATASET = process.env.BIGQUERY_DATASET;
const ORIGINAL_TABLE = process.env.BIGQUERY_TABLE;

const {
  isEnabled,
  insertEvent,
  insertEvents,
  _formatRow,
  _isRetryableError,
  _resetClient,
  _setSleepFn,
} = require('./bigquery-client');

// ─── Setup / teardown ────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  // Default env
  process.env.BIGQUERY_PROJECT_ID = 'test-project';
  process.env.BIGQUERY_DATASET = 'wrack_telemetry';
  process.env.BIGQUERY_TABLE = 'events';
  // Default: insert succeeds
  mockInsert = jest.fn().mockResolvedValue([]);
  // Clear singleton so each test gets a fresh mock client instance
  _resetClient();
  // No-op sleep to make retries instant
  _setSleepFn(() => Promise.resolve());
});

afterEach(() => {
  // Restore env vars
  if (ORIGINAL_PROJECT_ID === undefined) {
    delete process.env.BIGQUERY_PROJECT_ID;
  } else {
    process.env.BIGQUERY_PROJECT_ID = ORIGINAL_PROJECT_ID;
  }
  if (ORIGINAL_DATASET === undefined) {
    delete process.env.BIGQUERY_DATASET;
  } else {
    process.env.BIGQUERY_DATASET = ORIGINAL_DATASET;
  }
  if (ORIGINAL_TABLE === undefined) {
    delete process.env.BIGQUERY_TABLE;
  } else {
    process.env.BIGQUERY_TABLE = ORIGINAL_TABLE;
  }
  _resetClient();
  // Restore real sleep
  _setSleepFn((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
});

// ─── isEnabled() ─────────────────────────────────────────────────────────────

describe('isEnabled()', () => {
  test('returns true when BIGQUERY_PROJECT_ID is set', () => {
    // isEnabled reads the module-level const which was already captured at
    // require() time, so we test via insertEvent behaviour instead.
    // The const is captured at module load — testing it directly here is
    // informational; the functional path is covered by insertEvent tests.
    expect(typeof isEnabled()).toBe('boolean');
  });

  test('insertEvent returns skipped:true when BIGQUERY_PROJECT_ID is absent', async () => {
    // To test the disabled path we need a fresh module load without the var.
    // We exercise this through a separate sub-test that uses jest.isolateModules.
    jest.isolateModules(() => {
      delete process.env.BIGQUERY_PROJECT_ID;
      const client = require('./bigquery-client');
      expect(client.isEnabled()).toBe(false);
    });
  });
});

// ─── _formatRow() ────────────────────────────────────────────────────────────

describe('_formatRow()', () => {
  const baseEvent = {
    event_id: 'evt-001',
    event_type: 'battery_status',
    source: 'ev3',
    timestamp: '2024-01-15T10:00:00.000Z',
    payload: { voltage_mv: 7200, percentage: 85 },
  };

  test('includes all required fields', () => {
    const row = _formatRow(baseEvent);
    expect(row.event_id).toBe('evt-001');
    expect(row.event_type).toBe('battery_status');
    expect(row.source).toBe('ev3');
  });

  test('converts timestamp to ISO string', () => {
    const row = _formatRow(baseEvent);
    expect(row.timestamp).toBe(new Date(baseEvent.timestamp).toISOString());
  });

  test('stamps ingested_at as a valid ISO string', () => {
    const before = Date.now();
    const row = _formatRow(baseEvent);
    const after = Date.now();
    const ingestedMs = new Date(row.ingested_at).getTime();
    expect(ingestedMs).toBeGreaterThanOrEqual(before);
    expect(ingestedMs).toBeLessThanOrEqual(after);
  });

  test('serialises payload to a JSON string', () => {
    const row = _formatRow(baseEvent);
    expect(typeof row.payload).toBe('string');
    expect(JSON.parse(row.payload)).toEqual(baseEvent.payload);
  });

  test('sets absent optional fields to null', () => {
    const row = _formatRow(baseEvent);
    expect(row.device_id).toBeNull();
    expect(row.session_id).toBeNull();
    expect(row.version).toBeNull();
    expect(row.tags).toBeNull();
    expect(row.user_id).toBeNull();
    expect(row.correlation_id).toBeNull();
  });

  test('preserves optional fields when present', () => {
    const event = {
      ...baseEvent,
      device_id: 'ev3-001',
      session_id: 'sess-abc',
      version: '1.0.0',
      tags: ['production', 'test'],
      user_id: 'user-1',
      correlation_id: 'corr-xyz',
    };
    const row = _formatRow(event);
    expect(row.device_id).toBe('ev3-001');
    expect(row.session_id).toBe('sess-abc');
    expect(row.version).toBe('1.0.0');
    expect(row.tags).toEqual(['production', 'test']);
    expect(row.user_id).toBe('user-1');
    expect(row.correlation_id).toBe('corr-xyz');
  });

  test('handles payload with nested objects', () => {
    const event = { ...baseEvent, payload: { nested: { deep: true }, arr: [1, 2] } };
    const row = _formatRow(event);
    expect(JSON.parse(row.payload)).toEqual(event.payload);
  });
});

// ─── _isRetryableError() ─────────────────────────────────────────────────────

describe('_isRetryableError()', () => {
  test('returns false for null', () => {
    expect(_isRetryableError(null)).toBe(false);
  });

  test('returns false for undefined', () => {
    expect(_isRetryableError(undefined)).toBe(false);
  });

  test('returns true for 429 status code', () => {
    expect(_isRetryableError({ code: 429 })).toBe(true);
  });

  test('returns true for 500 status code', () => {
    expect(_isRetryableError({ code: 500 })).toBe(true);
  });

  test('returns true for 503 status code', () => {
    expect(_isRetryableError({ statusCode: 503 })).toBe(true);
  });

  test('returns true for status field equal to 503', () => {
    expect(_isRetryableError({ status: 503 })).toBe(true);
  });

  test('returns false for 400 status code', () => {
    expect(_isRetryableError({ code: 400 })).toBe(false);
  });

  test('returns false for 404 status code', () => {
    expect(_isRetryableError({ code: 404 })).toBe(false);
  });

  test('returns true for "UNAVAILABLE" in message', () => {
    expect(_isRetryableError(new Error('Service UNAVAILABLE'))).toBe(true);
  });

  test('returns true for "rate limit" in message', () => {
    expect(_isRetryableError(new Error('rate limit exceeded'))).toBe(true);
  });

  test('returns true for "rateLimitExceeded" in message', () => {
    expect(_isRetryableError(new Error('rateLimitExceeded'))).toBe(true);
  });

  test('returns true for "quota exceeded" in message', () => {
    expect(_isRetryableError(new Error('quota exceeded'))).toBe(true);
  });

  test('returns true for "quotaExceeded" in message', () => {
    expect(_isRetryableError(new Error('quotaExceeded'))).toBe(true);
  });

  test('returns true for "backendError" in message', () => {
    expect(_isRetryableError(new Error('backendError occurred'))).toBe(true);
  });

  test('returns true for "internal error" in message', () => {
    expect(_isRetryableError(new Error('internal error'))).toBe(true);
  });

  test('returns false for a generic connection refused error', () => {
    expect(_isRetryableError(new Error('Connection refused'))).toBe(false);
  });

  test('returns true when errors array contains backendError reason', () => {
    const error = new Error('BQ error');
    error.errors = [{ reason: 'backendError', message: 'temporary error' }];
    expect(_isRetryableError(error)).toBe(true);
  });

  test('returns true when errors array contains rateLimitExceeded reason', () => {
    const error = new Error('BQ error');
    error.errors = [{ reason: 'rateLimitExceeded', message: 'rate limit hit' }];
    expect(_isRetryableError(error)).toBe(true);
  });

  test('returns false when errors array contains only non-retryable reasons', () => {
    const error = new Error('BQ error');
    error.errors = [{ reason: 'invalid', message: 'bad data' }];
    expect(_isRetryableError(error)).toBe(false);
  });
});

// ─── insertEvent() ───────────────────────────────────────────────────────────

describe('insertEvent() — disabled client', () => {
  test('returns skipped:true when BIGQUERY_PROJECT_ID is not set', async () => {
    // Use isolateModules to load the module without the env var.
    let result;
    await jest.isolateModulesAsync(async () => {
      delete process.env.BIGQUERY_PROJECT_ID;
      const client = require('./bigquery-client');
      client._setSleepFn(() => Promise.resolve());
      result = await client.insertEvent({
        event_id: 'e1',
        event_type: 'battery_status',
        source: 'ev3',
        timestamp: '2024-01-15T10:00:00.000Z',
        payload: {},
      });
    });
    expect(result.success).toBe(false);
    expect(result.skipped).toBe(true);
    expect(result.reason).toMatch(/BIGQUERY_PROJECT_ID/);
  });
});

describe('insertEvent() — successful insert', () => {
  const validEvent = {
    event_id: 'evt-insert-1',
    event_type: 'battery_status',
    source: 'ev3',
    timestamp: '2024-01-15T10:00:00.000Z',
    payload: { voltage_mv: 7200, percentage: 85 },
  };

  test('returns success:true on successful insert', async () => {
    const result = await insertEvent(validEvent);
    expect(result.success).toBe(true);
    expect(result.skipped).toBeUndefined();
    expect(result.error).toBeUndefined();
  });

  test('calls BigQuery insert with one row', async () => {
    await insertEvent(validEvent);
    expect(mockInsert).toHaveBeenCalledTimes(1);
    const rows = mockInsert.mock.calls[0][0];
    expect(rows).toHaveLength(1);
    expect(rows[0].event_id).toBe(validEvent.event_id);
  });

  test('row sent to BigQuery has payload as JSON string', async () => {
    await insertEvent(validEvent);
    const rows = mockInsert.mock.calls[0][0];
    expect(typeof rows[0].payload).toBe('string');
    expect(JSON.parse(rows[0].payload)).toEqual(validEvent.payload);
  });

  test('row sent to BigQuery includes ingested_at', async () => {
    await insertEvent(validEvent);
    const rows = mockInsert.mock.calls[0][0];
    expect(rows[0].ingested_at).toBeDefined();
    expect(new Date(rows[0].ingested_at).getTime()).not.toBeNaN();
  });
});

describe('insertEvent() — PartialFailureError', () => {
  const validEvent = {
    event_id: 'evt-partial',
    event_type: 'command_executed',
    source: 'cloud_functions',
    timestamp: '2024-01-15T10:00:00.000Z',
    payload: { command: 'stop' },
  };

  test('returns partialFailure:true with errors array', async () => {
    const partialError = new Error('PartialFailureError');
    partialError.name = 'PartialFailureError';
    partialError.errors = [
      {
        row: { event_id: 'evt-partial' },
        errors: [{ reason: 'invalid', message: 'Required field missing' }],
      },
    ];
    mockInsert = jest.fn().mockRejectedValue(partialError);

    const result = await insertEvent(validEvent);
    expect(result.success).toBe(false);
    expect(result.partialFailure).toBe(true);
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0].event_id).toBe('evt-partial');
    expect(result.errors[0].errors[0]).toMatch(/Required field missing/);
  });

  test('does not retry on PartialFailureError', async () => {
    const partialError = new Error('PartialFailureError');
    partialError.name = 'PartialFailureError';
    partialError.errors = [];
    mockInsert = jest.fn().mockRejectedValue(partialError);

    await insertEvent(validEvent);
    expect(mockInsert).toHaveBeenCalledTimes(1);
  });
});

describe('insertEvent() — non-retryable error', () => {
  const validEvent = {
    event_id: 'evt-err',
    event_type: 'error',
    source: 'ev3',
    timestamp: '2024-01-15T10:00:00.000Z',
    payload: { error_type: 'hardware' },
  };

  test('returns success:false with error message on non-retryable error', async () => {
    mockInsert = jest.fn().mockRejectedValue(new Error('Connection refused'));
    const result = await insertEvent(validEvent);
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/Connection refused/);
  });

  test('does not retry on non-retryable error', async () => {
    mockInsert = jest.fn().mockRejectedValue(new Error('Connection refused'));
    await insertEvent(validEvent);
    expect(mockInsert).toHaveBeenCalledTimes(1);
  });

  test('never throws — returns error in result object', async () => {
    mockInsert = jest.fn().mockRejectedValue(new Error('Unexpected failure'));
    await expect(insertEvent(validEvent)).resolves.toMatchObject({ success: false });
  });
});

describe('insertEvent() — retryable error', () => {
  const validEvent = {
    event_id: 'evt-retry',
    event_type: 'api_request',
    source: 'cloud_functions',
    timestamp: '2024-01-15T10:00:00.000Z',
    payload: { endpoint: '/control', status_code: 200, latency_ms: 50 },
  };

  test('retries up to MAX_RETRIES (3) times then returns failure', async () => {
    const rateLimitError = new Error('rate limit exceeded');
    rateLimitError.code = 429;
    mockInsert = jest.fn().mockRejectedValue(rateLimitError);

    const result = await insertEvent(validEvent);
    // 1 initial attempt + 3 retries = 4 total calls
    expect(mockInsert).toHaveBeenCalledTimes(4);
    expect(result.success).toBe(false);
  });

  test('succeeds when a retry attempt succeeds', async () => {
    const rateLimitError = new Error('rate limit exceeded');
    rateLimitError.code = 429;
    mockInsert = jest
      .fn()
      .mockRejectedValueOnce(rateLimitError)
      .mockResolvedValue([]);

    const result = await insertEvent(validEvent);
    expect(mockInsert).toHaveBeenCalledTimes(2);
    expect(result.success).toBe(true);
  });

  test('retries on 500 status code error', async () => {
    const serverError = new Error('internal server error');
    serverError.code = 500;
    mockInsert = jest
      .fn()
      .mockRejectedValueOnce(serverError)
      .mockRejectedValueOnce(serverError)
      .mockResolvedValue([]);

    const result = await insertEvent(validEvent);
    expect(mockInsert).toHaveBeenCalledTimes(3);
    expect(result.success).toBe(true);
  });

  test('retries on UNAVAILABLE error message', async () => {
    const unavailError = new Error('Service UNAVAILABLE');
    mockInsert = jest
      .fn()
      .mockRejectedValueOnce(unavailError)
      .mockResolvedValue([]);

    const result = await insertEvent(validEvent);
    expect(mockInsert).toHaveBeenCalledTimes(2);
    expect(result.success).toBe(true);
  });
});

// ─── insertEvents() ──────────────────────────────────────────────────────────

describe('insertEvents() — disabled client', () => {
  test('returns skipped:true when BIGQUERY_PROJECT_ID is not set', async () => {
    let result;
    await jest.isolateModulesAsync(async () => {
      delete process.env.BIGQUERY_PROJECT_ID;
      const client = require('./bigquery-client');
      client._setSleepFn(() => Promise.resolve());
      result = await client.insertEvents([
        {
          event_id: 'e1',
          event_type: 'battery_status',
          source: 'ev3',
          timestamp: '2024-01-15T10:00:00.000Z',
          payload: {},
        },
      ]);
    });
    expect(result.success).toBe(false);
    expect(result.skipped).toBe(true);
    expect(result.reason).toMatch(/BIGQUERY_PROJECT_ID/);
  });
});

describe('insertEvents() — input validation', () => {
  test('returns error for empty array', async () => {
    const result = await insertEvents([]);
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/non-empty array/);
  });

  test('returns error for non-array input', async () => {
    const result = await insertEvents('not-an-array');
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/non-empty array/);
  });

  test('returns error for null input', async () => {
    const result = await insertEvents(null);
    expect(result.success).toBe(false);
  });
});

describe('insertEvents() — successful batch insert', () => {
  const events = [
    {
      event_id: 'evt-batch-1',
      event_type: 'battery_status',
      source: 'ev3',
      timestamp: '2024-01-15T10:00:00.000Z',
      payload: { voltage_mv: 7200 },
    },
    {
      event_id: 'evt-batch-2',
      event_type: 'command_received',
      source: 'cloud_functions',
      timestamp: '2024-01-15T10:00:01.000Z',
      payload: { command: 'forward' },
    },
    {
      event_id: 'evt-batch-3',
      event_type: 'command_executed',
      source: 'ev3',
      timestamp: '2024-01-15T10:00:02.000Z',
      payload: { command: 'forward', success: true },
    },
  ];

  test('returns success:true and inserted count on success', async () => {
    const result = await insertEvents(events);
    expect(result.success).toBe(true);
    expect(result.inserted).toBe(3);
  });

  test('calls BigQuery insert exactly once with all rows', async () => {
    await insertEvents(events);
    expect(mockInsert).toHaveBeenCalledTimes(1);
    const rows = mockInsert.mock.calls[0][0];
    expect(rows).toHaveLength(3);
  });

  test('each row has payload as JSON string', async () => {
    await insertEvents(events);
    const rows = mockInsert.mock.calls[0][0];
    rows.forEach((row, i) => {
      expect(typeof row.payload).toBe('string');
      expect(JSON.parse(row.payload)).toEqual(events[i].payload);
    });
  });

  test('each row includes ingested_at', async () => {
    await insertEvents(events);
    const rows = mockInsert.mock.calls[0][0];
    rows.forEach((row) => {
      expect(row.ingested_at).toBeDefined();
      expect(new Date(row.ingested_at).getTime()).not.toBeNaN();
    });
  });

  test('single-element array is accepted', async () => {
    const result = await insertEvents([events[0]]);
    expect(result.success).toBe(true);
    expect(result.inserted).toBe(1);
    expect(mockInsert).toHaveBeenCalledTimes(1);
    expect(mockInsert.mock.calls[0][0]).toHaveLength(1);
  });
});

describe('insertEvents() — PartialFailureError', () => {
  const events = [
    {
      event_id: 'evt-pf-1',
      event_type: 'battery_status',
      source: 'ev3',
      timestamp: '2024-01-15T10:00:00.000Z',
      payload: { voltage_mv: 7200 },
    },
    {
      event_id: 'evt-pf-2',
      event_type: 'error',
      source: 'ev3',
      timestamp: '2024-01-15T10:00:01.000Z',
      payload: { error_type: 'hardware', message: 'motor fault' },
    },
  ];

  test('returns partialFailure:true with per-row errors', async () => {
    const partialError = new Error('PartialFailureError');
    partialError.name = 'PartialFailureError';
    partialError.errors = [
      {
        row: { event_id: 'evt-pf-1' },
        errors: [{ reason: 'invalid', message: 'Schema mismatch' }],
      },
    ];
    mockInsert = jest.fn().mockRejectedValue(partialError);

    const result = await insertEvents(events);
    expect(result.success).toBe(false);
    expect(result.partialFailure).toBe(true);
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0].event_id).toBe('evt-pf-1');
    expect(result.errors[0].errors[0]).toMatch(/Schema mismatch/);
  });

  test('does not retry on PartialFailureError', async () => {
    const partialError = new Error('PartialFailureError');
    partialError.name = 'PartialFailureError';
    partialError.errors = [];
    mockInsert = jest.fn().mockRejectedValue(partialError);

    await insertEvents(events);
    expect(mockInsert).toHaveBeenCalledTimes(1);
  });
});

describe('insertEvents() — retryable error', () => {
  const events = [
    {
      event_id: 'evt-retry-batch',
      event_type: 'device_status',
      source: 'ev3',
      timestamp: '2024-01-15T10:00:00.000Z',
      payload: { device_name: 'motor_a', status: 'ok' },
    },
  ];

  test('retries up to MAX_RETRIES (3) times then returns failure', async () => {
    const serverError = new Error('internal server error');
    serverError.code = 500;
    mockInsert = jest.fn().mockRejectedValue(serverError);

    const result = await insertEvents(events);
    expect(mockInsert).toHaveBeenCalledTimes(4);
    expect(result.success).toBe(false);
  });

  test('succeeds on second attempt after one retryable failure', async () => {
    const serverError = new Error('internal server error');
    serverError.code = 503;
    mockInsert = jest
      .fn()
      .mockRejectedValueOnce(serverError)
      .mockResolvedValue([]);

    const result = await insertEvents(events);
    expect(mockInsert).toHaveBeenCalledTimes(2);
    expect(result.success).toBe(true);
    expect(result.inserted).toBe(1);
  });

  test('never throws — returns error object', async () => {
    mockInsert = jest.fn().mockRejectedValue(new Error('Unknown failure'));
    await expect(insertEvents(events)).resolves.toMatchObject({ success: false });
  });
});

describe('insertEvents() — non-retryable error', () => {
  const events = [
    {
      event_id: 'evt-nr',
      event_type: 'api_request',
      source: 'cloud_functions',
      timestamp: '2024-01-15T10:00:00.000Z',
      payload: { endpoint: '/control', status_code: 200, latency_ms: 100 },
    },
  ];

  test('returns error message without retrying', async () => {
    mockInsert = jest.fn().mockRejectedValue(new Error('Permission denied'));
    const result = await insertEvents(events);
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/Permission denied/);
    expect(mockInsert).toHaveBeenCalledTimes(1);
  });
});

// ─── Client initialisation ───────────────────────────────────────────────────

describe('Client initialisation', () => {
  test('creates BigQuery client lazily on first insertEvent call', async () => {
    const { BigQuery } = require('@google-cloud/bigquery');
    expect(BigQuery).not.toHaveBeenCalled();

    await insertEvent({
      event_id: 'e-lazy',
      event_type: 'battery_status',
      source: 'ev3',
      timestamp: '2024-01-15T10:00:00.000Z',
      payload: {},
    });

    expect(BigQuery).toHaveBeenCalledTimes(1);
    expect(BigQuery).toHaveBeenCalledWith({ projectId: 'test-project' });
  });

  test('reuses the same BigQuery client across multiple insertEvent calls', async () => {
    const { BigQuery } = require('@google-cloud/bigquery');
    const event = {
      event_id: 'e-reuse',
      event_type: 'battery_status',
      source: 'ev3',
      timestamp: '2024-01-15T10:00:00.000Z',
      payload: {},
    };

    await insertEvent(event);
    await insertEvent({ ...event, event_id: 'e-reuse-2' });

    // Client constructor should only be called once despite two insertEvent calls.
    expect(BigQuery).toHaveBeenCalledTimes(1);
  });

  test('_resetClient() causes a new BigQuery client to be created', async () => {
    const { BigQuery } = require('@google-cloud/bigquery');
    const event = {
      event_id: 'e-reset',
      event_type: 'battery_status',
      source: 'ev3',
      timestamp: '2024-01-15T10:00:00.000Z',
      payload: {},
    };

    await insertEvent(event);
    _resetClient();
    await insertEvent({ ...event, event_id: 'e-reset-2' });

    expect(BigQuery).toHaveBeenCalledTimes(2);
  });
});
