'use strict';

const { SeverityNumber } = require('@opentelemetry/api-logs');
const { mapEventToMetricPoints, mapEventToLogRecord, _severityForEvent } = require('./otlp-mapper');

function baseEvent(overrides = {}) {
  return {
    event_id: 'evt-001',
    event_type: 'battery_status',
    source: 'ev3',
    device_id: 'ev3-001',
    timestamp: '2024-01-15T10:00:00.000Z',
    payload: { voltage_mv: 7200, percentage: 85 },
    ...overrides,
  };
}

describe('mapEventToMetricPoints()', () => {
  test('emits one gauge point per numeric payload field', () => {
    const points = mapEventToMetricPoints(baseEvent());
    expect(points).toEqual(
      expect.arrayContaining([
        { name: 'wrack.battery_status.voltage_mv', value: 7200, attributes: expect.any(Object) },
        { name: 'wrack.battery_status.percentage', value: 85, attributes: expect.any(Object) },
      ])
    );
    expect(points).toHaveLength(2);
  });

  test('metric names are namespaced by event_type', () => {
    const points = mapEventToMetricPoints(baseEvent({ event_type: 'device_status', payload: { uptime_seconds: 42 } }));
    expect(points[0].name).toBe('wrack.device_status.uptime_seconds');
  });

  test('coerces boolean fields to 1/0', () => {
    const points = mapEventToMetricPoints(
      baseEvent({ payload: { voltage_mv: 7200, is_critical: true, charging: false } })
    );
    const byName = Object.fromEntries(points.map((p) => [p.name, p.value]));
    expect(byName['wrack.battery_status.is_critical']).toBe(1);
    expect(byName['wrack.battery_status.charging']).toBe(0);
  });

  test('skips non-numeric, non-boolean fields (e.g. strings, nested objects)', () => {
    const points = mapEventToMetricPoints(
      baseEvent({
        event_type: 'device_status',
        payload: { device_name: 'ev3', status: 'connected', context: { foo: 'bar' } },
      })
    );
    expect(points).toHaveLength(0);
  });

  test('PEN-200: EV3 heartbeat motor-availability booleans map to wrack.device_status.<field> gauges', () => {
    const points = mapEventToMetricPoints(
      baseEvent({
        event_type: 'device_status',
        payload: {
          device_name: 'ev3',
          status: 'connected',
          voltage_mv: 7500,
          motor_l_available: true,
          motor_r_available: true,
          turret_available: false,
        },
      })
    );
    const byName = Object.fromEntries(points.map((p) => [p.name, p.value]));
    expect(byName['wrack.device_status.voltage_mv']).toBe(7500);
    expect(byName['wrack.device_status.motor_l_available']).toBe(1);
    expect(byName['wrack.device_status.motor_r_available']).toBe(1);
    expect(byName['wrack.device_status.turret_available']).toBe(0);
  });

  test('excludes NaN/Infinity from payload values', () => {
    const points = mapEventToMetricPoints(baseEvent({ payload: { voltage_mv: NaN, percentage: Infinity, ok: 1 } }));
    expect(points).toHaveLength(1);
    expect(points[0].name).toBe('wrack.battery_status.ok');
  });

  test('returns an empty array for an event with no payload fields', () => {
    expect(mapEventToMetricPoints(baseEvent({ payload: {} }))).toEqual([]);
  });

  test('attributes include device_id, source, event_type, and session_id when present', () => {
    const points = mapEventToMetricPoints(baseEvent({ session_id: 'sess-abc' }));
    expect(points[0].attributes).toEqual({
      event_type: 'battery_status',
      source: 'ev3',
      device_id: 'ev3-001',
      session_id: 'sess-abc',
    });
  });

  test('omits device_id/session_id attributes when absent rather than sending them empty', () => {
    const points = mapEventToMetricPoints(baseEvent({ device_id: null, session_id: undefined }));
    expect(points[0].attributes).toEqual({ event_type: 'battery_status', source: 'ev3' });
  });

  test('every metric point shares the same attributes object shape for a given event', () => {
    const points = mapEventToMetricPoints(baseEvent());
    expect(points[0].attributes).toEqual(points[1].attributes);
  });
});

describe('_severityForEvent()', () => {
  test('defaults to INFO for a routine health record', () => {
    expect(_severityForEvent(baseEvent())).toEqual({ severityNumber: SeverityNumber.INFO, severityText: 'INFO' });
  });

  test('elevates event_type "error" to ERROR', () => {
    expect(_severityForEvent(baseEvent({ event_type: 'error', payload: { error_type: 'device_error', message: 'x' } }))).toEqual({
      severityNumber: SeverityNumber.ERROR,
      severityText: 'ERROR',
    });
  });

  test.each(['error', 'disconnected', 'stalled'])(
    'elevates device_status with status "%s" to WARN',
    (status) => {
      expect(
        _severityForEvent(baseEvent({ event_type: 'device_status', payload: { device_name: 'ev3', status } }))
      ).toEqual({ severityNumber: SeverityNumber.WARN, severityText: 'WARN' });
    }
  );

  test.each(['connected', 'initializing'])('keeps device_status with status "%s" at INFO', (status) => {
    expect(
      _severityForEvent(baseEvent({ event_type: 'device_status', payload: { device_name: 'ev3', status } }))
    ).toEqual({ severityNumber: SeverityNumber.INFO, severityText: 'INFO' });
  });
});

describe('mapEventToLogRecord()', () => {
  test('carries the full payload as a JSON-stringified body', () => {
    const record = mapEventToLogRecord(baseEvent());
    expect(JSON.parse(record.body)).toEqual({ voltage_mv: 7200, percentage: 85 });
  });

  test('attributes include event_id and correlation_id when present', () => {
    const record = mapEventToLogRecord(baseEvent({ correlation_id: 'corr-1' }));
    expect(record.attributes).toEqual({
      event_type: 'battery_status',
      source: 'ev3',
      device_id: 'ev3-001',
      event_id: 'evt-001',
      correlation_id: 'corr-1',
    });
  });

  test('omits correlation_id from attributes when absent', () => {
    const record = mapEventToLogRecord(baseEvent());
    expect('correlation_id' in record.attributes).toBe(false);
  });

  test('timestampMs reflects the event timestamp', () => {
    const record = mapEventToLogRecord(baseEvent({ timestamp: '2024-01-15T10:00:00.000Z' }));
    expect(record.timestampMs).toBe(Date.parse('2024-01-15T10:00:00.000Z'));
  });

  test('falls back to Date.now() for a missing/invalid timestamp instead of producing NaN', () => {
    const nowSpy = jest.spyOn(Date, 'now').mockReturnValue(1_700_000_000_000);
    expect(mapEventToLogRecord(baseEvent({ timestamp: 'not-a-date' })).timestampMs).toBe(1_700_000_000_000);
    expect(mapEventToLogRecord(baseEvent({ timestamp: undefined })).timestampMs).toBe(1_700_000_000_000);
    nowSpy.mockRestore();
  });

  test('severity matches _severityForEvent() for the same event', () => {
    const event = baseEvent({ event_type: 'device_status', payload: { device_name: 'ev3', status: 'error' } });
    const record = mapEventToLogRecord(event);
    expect(record.severityNumber).toBe(SeverityNumber.WARN);
    expect(record.severityText).toBe('WARN');
  });

  test('defaults an empty payload to "{}" rather than throwing', () => {
    const record = mapEventToLogRecord(baseEvent({ payload: undefined }));
    expect(record.body).toBe('{}');
  });
});
