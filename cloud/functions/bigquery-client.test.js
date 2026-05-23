'use strict';

// ---------------------------------------------------------------------------
// Mock @google-cloud/bigquery before requiring the module under test
// ---------------------------------------------------------------------------

const mockInsert = jest.fn();
const mockTable = jest.fn(() => ({ insert: mockInsert }));
const mockDataset = jest.fn(() => ({ table: mockTable }));
const MockBigQuery = jest.fn(() => ({ dataset: mockDataset }));

jest.mock('@google-cloud/bigquery', () => ({
  BigQuery: MockBigQuery,
}));

const {
  isEnabled,
  insertEvent,
  insertEvents,
  _formatRow,
  _isRetryableError,
  _reset,
} = require('./bigquery-client');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const VALID_EVENT = {
  event_id: '123e4567-e89b-12d3-a456-426614174000',
  event_type: 'api_request',
  source: 'cloud_functions',
  timestamp: '2026-01-01T00:00:00.000Z',
  payload: { endpoint: '/controlRobot', status_code: 200, latency_ms: 50 },
};

function setEnv(overrides = {}) {
  const defaults = {
    BIGQUERY_PROJECT_ID: 'test-project',
    BIGQUERY_DATASET: 'wrack_telemetry',
    BIGQUERY_TABLE: 'events',
  };
  Object.assign(process.env, defaults, overrides);
}

function clearBQEnv() {
  delete process.env.BIGQUERY_PROJECT_ID;
  delete process.env.BIGQUERY_DATASET;
  delete process.env.BIGQUERY_TABLE;
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  jest.clearAllMocks();
  _reset();
  setEnv();
});

afterEach(() => {
  clearBQEnv();
});

// ---------------------------------------------------------------------------
// isEnabled()
// ---------------------------------------------------------------------------

describe('isEnabled()', () => {
  test('returns true when BIGQUERY_PROJECT_ID is set', () => {
    process.env.BIGQUERY_PROJECT_ID = 'my-project';
    expect(isEnabled()).toBe(true);
  });

  test('returns false when BIGQUERY_PROJECT_ID is not set', () => {
    delete process.env.BIGQUERY_PROJECT_ID;
    expect(isEnabled()).toBe(false);
  });

  test('returns false when BIGQUERY_PROJECT_ID is an empty string', () => {
    process.env.BIGQUERY_PROJECT_ID = '';
    expect(isEnabled()).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// _formatRow()
// ---------------------------------------------------------------------------

describe('_formatRow()', () => {
  test('maps all required fields from event envelope', () => {
    const row = _formatRow(VALID_EVENT);

    expect(row.event_id).toBe(VALID_EVENT.event_id);
    expect(row.event_type).toBe(VALID_EVENT.event_type);
    expect(row.source).toBe(VALID_EVENT.source);
    expect(row.timestamp).toBe(VALID_EVENT.timestamp);
  });

  test('serialises payload object to JSON string', () => {
    const row = _formatRow(VALID_EVENT);
    expect(typeof row.payload).toBe('string');
    expect(JSON.parse(row.payload)).toEqual(VALID_EVENT.payload);
  });

  test('leaves payload alone when already a string', () => {
    const event = { ...VALID_EVENT, payload: '{"pre":"serialised"}' };
    const row = _formatRow(event);
    expect(row.payload).toBe('{"pre":"serialised"}');
  });

  test('adds ingested_at as an ISO 8601 UTC string', () => {
    const before = new Date();
    const row = _formatRow(VALID_EVENT);
    const after = new Date();

    const ingestedAt = new Date(row.ingested_at);
    expect(ingestedAt.getTime()).toBeGreaterThanOrEqual(before.getTime());
    expect(ingestedAt.getTime()).toBeLessThanOrEqual(after.getTime());
    expect(row.ingested_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  test('maps optional fields to null when absent', () => {
    const row = _formatRow(VALID_EVENT);
    expect(row.device_id).toBeNull();
    expect(row.session_id).toBeNull();
    expect(row.version).toBeNull();
    expect(row.tags).toBeNull();
    expect(row.user_id).toBeNull();
    expect(row.correlation_id).toBeNull();
  });

  test('maps optional fields when present', () => {
    const event = {
      ...VALID_EVENT,
      device_id: 'ev3-001',
      session_id: 'sess-abc',
      version: '1.0',
      tags: ['prod', 'europe'],
      user_id: 'user-xyz',
      correlation_id: 'corr-123',
    };
    const row = _formatRow(event);

    expect(row.device_id).toBe('ev3-001');
    expect(row.session_id).toBe('sess-abc');
    expect(row.version).toBe('1.0');
    expect(row.tags).toEqual(['prod', 'europe']);
    expect(row.user_id).toBe('user-xyz');
    expect(row.correlation_id).toBe('corr-123');
  });

  test('sets tags to null when it is not an array', () => {
    const row = _formatRow({ ...VALID_EVENT, tags: 'not-an-array' });
    expect(row.tags).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// _isRetryableError()
// ---------------------------------------------------------------------------

describe('_isRetryableError()', () => {
  test.each([429, 500, 502, 503, 504])(
    'returns true for HTTP status code %i',
    (code) => {
      expect(_isRetryableError({ code })).toBe(true);
    }
  );

  test.each([400, 401, 403, 404])(
    'returns false for non-retryable status code %i',
    (code) => {
      expect(_isRetryableError({ code })).toBe(false);
    }
  );

  test('returns true for UNAVAILABLE message', () => {
    expect(_isRetryableError({ message: 'Service unavailable' })).toBe(true);
  });

  test('returns true for rate limit message', () => {
    expect(_isRetryableError({ message: 'Rate limit exceeded' })).toBe(true);
  });

  test('returns true for quota exceeded message', () => {
    expect(_isRetryableError({ message: 'Quota exceeded for project' })).toBe(true);
  });

  test('returns false for schema validation error', () => {
    expect(_isRetryableError({ message: 'Invalid schema: field mismatch' })).toBe(false);
  });

  test('returns false for null', () => {
    expect(_isRetryableError(null)).toBe(false);
  });

  test('returns false for undefined', () => {
    expect(_isRetryableError(undefined)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// insertEvent()
// ---------------------------------------------------------------------------

describe('insertEvent()', () => {
  test('inserts a valid event and returns success', async () => {
    mockInsert.mockResolvedValueOnce(undefined);

    const result = await insertEvent(VALID_EVENT);

    expect(result.success).toBe(true);
    expect(result.inserted).toBe(1);
    expect(result.failed).toBe(0);
    expect(mockInsert).toHaveBeenCalledTimes(1);
  });

  test('passes formatted row to BigQuery table.insert wrapped with insertId', async () => {
    mockInsert.mockResolvedValueOnce(undefined);

    await insertEvent(VALID_EVENT);

    const [rows] = mockInsert.mock.calls[0];
    expect(rows).toHaveLength(1);
    expect(rows[0].insertId).toBe(VALID_EVENT.event_id);
    expect(rows[0].json.event_id).toBe(VALID_EVENT.event_id);
    expect(rows[0].json.event_type).toBe(VALID_EVENT.event_type);
    expect(typeof rows[0].json.payload).toBe('string');
    expect(rows[0].json.ingested_at).toBeDefined();
  });

  test('returns error result for null input', async () => {
    const result = await insertEvent(null);

    expect(result.success).toBe(false);
    expect(result.failed).toBe(1);
    expect(result.error).toMatch(/invalid event/i);
    expect(mockInsert).not.toHaveBeenCalled();
  });

  test('returns error result for array input', async () => {
    const result = await insertEvent([VALID_EVENT]);

    expect(result.success).toBe(false);
    expect(result.failed).toBe(1);
    expect(mockInsert).not.toHaveBeenCalled();
  });

  test('returns error result when BigQuery not configured', async () => {
    delete process.env.BIGQUERY_PROJECT_ID;

    const result = await insertEvent(VALID_EVENT);

    expect(result.success).toBe(false);
    expect(result.inserted).toBe(0);
    expect(result.failed).toBe(1);
    expect(result.error).toMatch(/not configured/i);
    expect(mockInsert).not.toHaveBeenCalled();
  });

  test('returns error result when BigQuery insert throws', async () => {
    mockInsert.mockRejectedValueOnce(new Error('Network failure'));

    const result = await insertEvent(VALID_EVENT);

    expect(result.success).toBe(false);
    expect(result.failed).toBe(1);
    expect(result.error).toContain('Network failure');
  });
});

// ---------------------------------------------------------------------------
// insertEvents()
// ---------------------------------------------------------------------------

describe('insertEvents()', () => {
  test('inserts a batch of events and returns success', async () => {
    mockInsert.mockResolvedValueOnce(undefined);

    const events = [VALID_EVENT, { ...VALID_EVENT, event_id: 'another-id' }];
    const result = await insertEvents(events);

    expect(result.success).toBe(true);
    expect(result.inserted).toBe(2);
    expect(result.failed).toBe(0);
    expect(mockInsert).toHaveBeenCalledTimes(1);
  });

  test('sends all rows in a single insert call', async () => {
    mockInsert.mockResolvedValueOnce(undefined);

    const events = [
      VALID_EVENT,
      { ...VALID_EVENT, event_id: 'id-2' },
      { ...VALID_EVENT, event_id: 'id-3' },
    ];
    await insertEvents(events);

    const [rows] = mockInsert.mock.calls[0];
    expect(rows).toHaveLength(3);
  });

  test('returns success with zero inserts for empty array', async () => {
    const result = await insertEvents([]);

    expect(result.success).toBe(true);
    expect(result.inserted).toBe(0);
    expect(result.failed).toBe(0);
    expect(mockInsert).not.toHaveBeenCalled();
  });

  test('returns success with zero inserts for non-array input', async () => {
    const result = await insertEvents(null);

    expect(result.success).toBe(true);
    expect(result.inserted).toBe(0);
    expect(result.failed).toBe(0);
    expect(mockInsert).not.toHaveBeenCalled();
  });

  test('returns error result when BigQuery not configured', async () => {
    delete process.env.BIGQUERY_PROJECT_ID;

    const result = await insertEvents([VALID_EVENT]);

    expect(result.success).toBe(false);
    expect(result.inserted).toBe(0);
    expect(result.failed).toBe(1);
    expect(result.error).toMatch(/not configured/i);
    expect(mockInsert).not.toHaveBeenCalled();
  });

  test('handles PartialFailureError and returns partial result', async () => {
    const partialErr = Object.assign(new Error('Some rows failed'), {
      name: 'PartialFailureError',
      errors: [
        { row: { event_id: 'bad-id' }, errors: [{ message: 'Invalid value', reason: 'invalid' }] },
      ],
    });
    mockInsert.mockRejectedValueOnce(partialErr);

    const events = [VALID_EVENT, { ...VALID_EVENT, event_id: 'bad-id' }];
    const result = await insertEvents(events);

    expect(result.success).toBe(false);
    expect(result.inserted).toBe(1);
    expect(result.failed).toBe(1);
    expect(result.errors).toHaveLength(1);
  });

  test('returns full failure when a non-retryable error occurs', async () => {
    // Use a non-retryable error (400) so the test does not hang on real sleep delays
    mockInsert.mockRejectedValueOnce(Object.assign(new Error('Invalid schema'), { code: 400 }));

    const result = await insertEvents([VALID_EVENT, { ...VALID_EVENT, event_id: 'id-2' }]);

    expect(result.success).toBe(false);
    expect(result.inserted).toBe(0);
    expect(result.failed).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// Retry logic
// ---------------------------------------------------------------------------

describe('retry behaviour', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('retries on a retryable error and succeeds on the second attempt', async () => {
    const retryableErr = Object.assign(new Error('Service unavailable'), { code: 503 });
    mockInsert
      .mockRejectedValueOnce(retryableErr)
      .mockResolvedValueOnce(undefined);

    const promise = insertEvent(VALID_EVENT);
    await jest.runAllTimersAsync();
    const result = await promise;

    expect(result.success).toBe(true);
    expect(result.inserted).toBe(1);
    expect(mockInsert).toHaveBeenCalledTimes(2);
  });

  test('retries up to MAX_RETRIES (3) and then fails', async () => {
    const retryableErr = Object.assign(new Error('Rate limit exceeded'), { code: 429 });
    mockInsert.mockRejectedValue(retryableErr);

    const promise = insertEvent(VALID_EVENT);
    await jest.runAllTimersAsync();
    const result = await promise;

    // 1 initial attempt + 3 retries = 4 total calls
    expect(mockInsert).toHaveBeenCalledTimes(4);
    expect(result.success).toBe(false);
  });

  test('does not retry on a non-retryable error', async () => {
    const nonRetryable = Object.assign(new Error('Schema mismatch'), { code: 400 });
    mockInsert.mockRejectedValueOnce(nonRetryable);

    const promise = insertEvent(VALID_EVENT);
    await jest.runAllTimersAsync();
    const result = await promise;

    expect(mockInsert).toHaveBeenCalledTimes(1);
    expect(result.success).toBe(false);
  });

  test('does not retry on PartialFailureError', async () => {
    const partialErr = Object.assign(new Error('Row rejected'), {
      name: 'PartialFailureError',
      errors: [{ row: {}, errors: [] }],
    });
    mockInsert.mockRejectedValueOnce(partialErr);

    const promise = insertEvent(VALID_EVENT);
    await jest.runAllTimersAsync();
    await promise;

    expect(mockInsert).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// BigQuery client initialisation
// ---------------------------------------------------------------------------

describe('BigQuery client initialisation', () => {
  test('initialises BigQuery with BIGQUERY_PROJECT_ID from env', async () => {
    process.env.BIGQUERY_PROJECT_ID = 'my-gcp-project';
    mockInsert.mockResolvedValueOnce(undefined);

    await insertEvent(VALID_EVENT);

    expect(MockBigQuery).toHaveBeenCalledWith({ projectId: 'my-gcp-project' });
  });

  test('uses default dataset "wrack_telemetry" when BIGQUERY_DATASET is not set', async () => {
    delete process.env.BIGQUERY_DATASET;
    mockInsert.mockResolvedValueOnce(undefined);

    await insertEvent(VALID_EVENT);

    expect(mockDataset).toHaveBeenCalledWith('wrack_telemetry');
  });

  test('uses custom dataset from BIGQUERY_DATASET env var', async () => {
    process.env.BIGQUERY_DATASET = 'custom_dataset';
    mockInsert.mockResolvedValueOnce(undefined);

    await insertEvent(VALID_EVENT);

    expect(mockDataset).toHaveBeenCalledWith('custom_dataset');
  });

  test('uses default table "events" when BIGQUERY_TABLE is not set', async () => {
    delete process.env.BIGQUERY_TABLE;
    mockInsert.mockResolvedValueOnce(undefined);

    await insertEvent(VALID_EVENT);

    expect(mockTable).toHaveBeenCalledWith('events');
  });

  test('uses custom table from BIGQUERY_TABLE env var', async () => {
    process.env.BIGQUERY_TABLE = 'custom_table';
    mockInsert.mockResolvedValueOnce(undefined);

    await insertEvent(VALID_EVENT);

    expect(mockTable).toHaveBeenCalledWith('custom_table');
  });

  test('reuses the same client instance across calls (singleton)', async () => {
    mockInsert.mockResolvedValue(undefined);

    await insertEvent(VALID_EVENT);
    await insertEvent(VALID_EVENT);

    expect(MockBigQuery).toHaveBeenCalledTimes(1);
  });
});
