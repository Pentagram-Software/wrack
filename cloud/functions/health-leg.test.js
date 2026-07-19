'use strict';

/**
 * Unit tests for the healthLegPush Cloud Function (PEN-228).
 *
 * Strategy:
 *  - Mock @google-cloud/functions-framework so the registered handler is
 *    captured directly, same as ingress.test.js/telemetry.test.js.
 *  - Mock ./grafana-credentials so credential loading is controllable
 *    without touching Secret Manager.
 *  - Mock the two OTLP exporter classes at the module level, capturing the
 *    config each is constructed with and letting tests control the
 *    export() result — the real @opentelemetry/sdk-metrics/sdk-logs
 *    machinery (MeterProvider, Gauge, LoggerProvider) still runs for real,
 *    so this also exercises that the mapper output is accepted by the SDK.
 */

let mockGetGrafanaCredentials;
let mockMetricExport;
let mockLogExport;
let mockCapturedMetricConfigs;
let mockCapturedLogConfigs;

jest.mock('@google-cloud/functions-framework', () => ({
  http: jest.fn(),
}));

jest.mock('./grafana-credentials', () => ({
  getGrafanaCredentials: (...args) => mockGetGrafanaCredentials(...args),
}));

jest.mock('@opentelemetry/exporter-metrics-otlp-http', () => ({
  OTLPMetricExporter: jest.fn().mockImplementation((config) => {
    mockCapturedMetricConfigs.push(config);
    return {
      export: (data, cb) => mockMetricExport(data, cb),
      forceFlush: () => Promise.resolve(),
      shutdown: () => Promise.resolve(),
    };
  }),
}));

jest.mock('@opentelemetry/exporter-logs-otlp-http', () => ({
  OTLPLogExporter: jest.fn().mockImplementation((config) => {
    mockCapturedLogConfigs.push(config);
    return {
      export: (data, cb) => mockLogExport(data, cb),
      forceFlush: () => Promise.resolve(),
      shutdown: () => Promise.resolve(),
    };
  }),
}));

const { ExportResultCode } = require('@opentelemetry/core');
const functions = require('@google-cloud/functions-framework');
const { pushToGrafana, _basicAuthHeader } = require('./health-leg');

const VALID_CREDENTIALS = {
  otlp_endpoint: 'https://otlp-gateway-prod-xx-xxxx.grafana.net/otlp',
  instance_id: '123456',
  token: 'glc_test_token',
};

let healthLegHandler;

function healthEvent(overrides = {}) {
  return {
    event_id: 'evt-001',
    event_type: 'battery_status',
    source: 'ev3',
    device_id: 'ev3-001',
    timestamp: '2024-01-15T10:00:00.000Z',
    type: 'health',
    payload: { voltage_mv: 7200, percentage: 85 },
    ...overrides,
  };
}

function makeReq(overrides = {}) {
  return { method: 'POST', body: healthEvent(), ...overrides };
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
  };
  return res;
}

function invokeHandler(req, res) {
  return new Promise((resolve) => {
    const origJson = res.json.bind(res);
    res.json = (...args) => {
      origJson(...args);
      resolve();
      return res;
    };
    healthLegHandler(req, res);
  });
}

beforeAll(() => {
  const calls = functions.http.mock.calls;
  const matching = calls.filter((c) => c[0] === 'healthLegPush');
  expect(matching.length).toBeGreaterThan(0);
  healthLegHandler = matching[0][1];
});

beforeEach(() => {
  jest.clearAllMocks();
  mockCapturedMetricConfigs = [];
  mockCapturedLogConfigs = [];
  mockGetGrafanaCredentials = jest.fn().mockResolvedValue(VALID_CREDENTIALS);
  mockMetricExport = jest.fn((data, cb) => cb({ code: ExportResultCode.SUCCESS }));
  mockLogExport = jest.fn((data, cb) => cb({ code: ExportResultCode.SUCCESS }));
  jest.spyOn(console, 'error').mockImplementation(() => {});
  jest.spyOn(console, 'log').mockImplementation(() => {});
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('_basicAuthHeader()', () => {
  test('base64-encodes instance_id:token as a Basic auth header', () => {
    expect(_basicAuthHeader('123456', 'glc_test_token')).toBe(
      `Basic ${Buffer.from('123456:glc_test_token').toString('base64')}`
    );
  });
});

describe('pushToGrafana()', () => {
  test('constructs the metrics exporter against <endpoint>/v1/metrics with Basic auth', async () => {
    await pushToGrafana(healthEvent());
    expect(mockCapturedMetricConfigs).toHaveLength(1);
    expect(mockCapturedMetricConfigs[0].url).toBe('https://otlp-gateway-prod-xx-xxxx.grafana.net/otlp/v1/metrics');
    expect(mockCapturedMetricConfigs[0].headers.Authorization).toBe(_basicAuthHeader('123456', 'glc_test_token'));
  });

  test('constructs the logs exporter against <endpoint>/v1/logs with the same Basic auth', async () => {
    await pushToGrafana(healthEvent());
    expect(mockCapturedLogConfigs).toHaveLength(1);
    expect(mockCapturedLogConfigs[0].url).toBe('https://otlp-gateway-prod-xx-xxxx.grafana.net/otlp/v1/logs');
    expect(mockCapturedLogConfigs[0].headers.Authorization).toBe(_basicAuthHeader('123456', 'glc_test_token'));
  });

  test('strips a trailing slash from otlp_endpoint before appending the signal path', async () => {
    mockGetGrafanaCredentials.mockResolvedValue({ ...VALID_CREDENTIALS, otlp_endpoint: 'https://example.test/otlp/' });
    await pushToGrafana(healthEvent());
    expect(mockCapturedMetricConfigs[0].url).toBe('https://example.test/otlp/v1/metrics');
  });

  test('actually pushes a metric data point for each numeric payload field', async () => {
    await pushToGrafana(healthEvent());
    expect(mockMetricExport).toHaveBeenCalledTimes(1);
    const [resourceMetrics] = mockMetricExport.mock.calls[0];
    const metricNames = resourceMetrics.scopeMetrics.flatMap((sm) => sm.metrics.map((m) => m.descriptor.name));
    expect(metricNames).toEqual(
      expect.arrayContaining(['wrack.battery_status.voltage_mv', 'wrack.battery_status.percentage'])
    );
  });

  test('always pushes exactly one log record regardless of payload shape', async () => {
    await pushToGrafana(healthEvent());
    expect(mockLogExport).toHaveBeenCalledTimes(1);
    const [logRecords] = mockLogExport.mock.calls[0];
    expect(logRecords).toHaveLength(1);
    expect(JSON.parse(logRecords[0].body.stringValue || logRecords[0].body)).toEqual({
      voltage_mv: 7200,
      percentage: 85,
    });
  });

  test('does not construct a metrics exporter at all when the payload has no numeric fields', async () => {
    await pushToGrafana(
      healthEvent({ event_type: 'device_status', payload: { device_name: 'ev3', status: 'connected' } })
    );
    expect(mockCapturedMetricConfigs).toHaveLength(0);
    expect(mockMetricExport).not.toHaveBeenCalled();
    // The log leg still runs — no payload data is dropped just because
    // nothing in it was numeric.
    expect(mockLogExport).toHaveBeenCalledTimes(1);
  });

  test('does not throw when the metrics push fails downstream (fails open)', async () => {
    mockMetricExport = jest.fn((data, cb) =>
      cb({ code: ExportResultCode.FAILED, error: new Error('Grafana 500') })
    );
    await expect(pushToGrafana(healthEvent())).resolves.toBeUndefined();
    expect(console.error).toHaveBeenCalledWith(
      expect.stringContaining('metrics push failed'),
      expect.anything()
    );
  });

  test('does not throw when the logs push fails downstream (fails open)', async () => {
    mockLogExport = jest.fn((data, cb) => cb({ code: ExportResultCode.FAILED, error: new Error('Grafana 500') }));
    await expect(pushToGrafana(healthEvent())).resolves.toBeUndefined();
    expect(console.error).toHaveBeenCalledWith(expect.stringContaining('logs push failed'), expect.anything());
  });

  test('propagates a credential-loading failure (the one case that is not caught internally)', async () => {
    mockGetGrafanaCredentials.mockRejectedValue(new Error('PERMISSION_DENIED'));
    await expect(pushToGrafana(healthEvent())).rejects.toThrow('PERMISSION_DENIED');
  });
});

describe('healthLegPush handler', () => {
  test('returns 405 for a non-POST request', async () => {
    const res = makeRes();
    await invokeHandler(makeReq({ method: 'GET' }), res);
    expect(res.statusCode).toBe(405);
  });

  test.each([
    ['null body', null],
    ['array body', []],
    ['a string', 'not-an-object'],
    ['missing event_id', { event_type: 'battery_status', payload: {} }],
  ])('returns 400 for %s', async (_label, body) => {
    const res = makeRes();
    await invokeHandler(makeReq({ body }), res);
    expect(res.statusCode).toBe(400);
  });

  test('returns 200 on a successful push', async () => {
    const res = makeRes();
    await invokeHandler(makeReq(), res);
    expect(res.statusCode).toBe(200);
    expect(res.data).toEqual({ success: true });
  });

  test('returns 200 even when the downstream OTLP push itself failed (fail open all the way to the caller)', async () => {
    mockMetricExport = jest.fn((data, cb) => cb({ code: ExportResultCode.FAILED, error: new Error('boom') }));
    const res = makeRes();
    await invokeHandler(makeReq(), res);
    expect(res.statusCode).toBe(200);
  });

  test('returns 502 when credentials cannot be loaded, and logs the failure', async () => {
    mockGetGrafanaCredentials.mockRejectedValue(new Error('Secret Manager unavailable'));
    const res = makeRes();
    await invokeHandler(makeReq(), res);
    expect(res.statusCode).toBe(502);
    expect(res.data.success).toBe(false);
    expect(console.error).toHaveBeenCalledWith(
      expect.stringContaining('push failed for event evt-001'),
      expect.anything()
    );
  });
});
