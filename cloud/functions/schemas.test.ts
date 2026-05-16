/**
 * Unit tests for cloud/functions/schemas.ts — telemetry event validation.
 */

import {
  VALID_EVENT_TYPES,
  VALID_SOURCES,
  P0_EVENT_TYPES,
  validateEventEnvelope,
  validateTelemetryEvent,
  validateTelemetryEventBatch,
  isValidTelemetryEvent,
  validateBatteryStatusPayload,
  validateCommandReceivedPayload,
  validateCommandExecutedPayload,
  validateDeviceStatusPayload,
  validateErrorPayload,
  validateApiRequestPayload,
} from './schemas';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const makeUUID = () => '550e8400-e29b-41d4-a716-446655440000';
const makeTS = () => '2026-05-16T12:00:00Z';

function makeEvent(eventType: string, payload: Record<string, unknown>, overrides: Record<string, unknown> = {}) {
  return {
    event_id: makeUUID(),
    event_type: eventType,
    source: 'ev3',
    timestamp: makeTS(),
    payload,
    ...overrides,
  };
}

const batteryPayload = (overrides = {}) => ({
  voltage_mv: 7200,
  percentage: 85,
  ...overrides,
});

const commandReceivedPayload = (overrides = {}) => ({
  command: 'forward',
  ...overrides,
});

const commandExecutedPayload = (overrides = {}) => ({
  command: 'forward',
  success: true,
  ...overrides,
});

const deviceStatusPayload = (overrides = {}) => ({
  device_name: 'drive_L',
  status: 'connected',
  ...overrides,
});

const errorPayload = (overrides = {}) => ({
  error_type: 'device_error',
  message: 'Motor stalled',
  ...overrides,
});

const apiRequestPayload = (overrides = {}) => ({
  endpoint: 'controlRobot',
  status_code: 200,
  latency_ms: 120,
  ...overrides,
});

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

describe('Constants', () => {
  test('P0_EVENT_TYPES is a subset of VALID_EVENT_TYPES', () => {
    for (const t of P0_EVENT_TYPES) {
      expect(VALID_EVENT_TYPES).toContain(t);
    }
  });

  test('VALID_SOURCES includes ev3 and cloud_functions', () => {
    expect(VALID_SOURCES).toContain('ev3');
    expect(VALID_SOURCES).toContain('cloud_functions');
  });

  test('P0_EVENT_TYPES contains all six required types', () => {
    const required = [
      'battery_status', 'command_received', 'command_executed',
      'device_status', 'error', 'api_request',
    ];
    for (const t of required) {
      expect(P0_EVENT_TYPES).toContain(t);
    }
  });
});

// ---------------------------------------------------------------------------
// validateEventEnvelope
// ---------------------------------------------------------------------------

describe('validateEventEnvelope', () => {
  test('valid minimal event passes', () => {
    const result = validateEventEnvelope(makeEvent('battery_status', batteryPayload()));
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  test('null input fails', () => {
    const result = validateEventEnvelope(null);
    expect(result.valid).toBe(false);
    expect(result.errors[0].field).toBe('root');
  });

  test('string input fails', () => {
    const result = validateEventEnvelope('not an object');
    expect(result.valid).toBe(false);
  });

  test('missing event_id fails', () => {
    const event = makeEvent('battery_status', batteryPayload());
    delete (event as Record<string, unknown>).event_id;
    const result = validateEventEnvelope(event);
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field === 'event_id')).toBe(true);
  });

  test('invalid UUID event_id fails', () => {
    const result = validateEventEnvelope(makeEvent('battery_status', batteryPayload(), { event_id: 'not-a-uuid' }));
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field === 'event_id')).toBe(true);
  });

  test('invalid event_type fails', () => {
    const result = validateEventEnvelope(makeEvent('unknown_event', {}));
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field === 'event_type')).toBe(true);
  });

  test('invalid source fails', () => {
    const result = validateEventEnvelope(makeEvent('battery_status', batteryPayload(), { source: 'toaster' }));
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field === 'source')).toBe(true);
  });

  test('all valid sources pass', () => {
    for (const source of VALID_SOURCES) {
      const result = validateEventEnvelope(makeEvent('battery_status', batteryPayload(), { source }));
      expect(result.valid).toBe(true);
    }
  });

  test('timestamp without Z fails', () => {
    const result = validateEventEnvelope(
      makeEvent('battery_status', batteryPayload(), { timestamp: '2026-01-01T00:00:00+00:00' })
    );
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field === 'timestamp')).toBe(true);
  });

  test('timestamp as date-only fails', () => {
    const result = validateEventEnvelope(
      makeEvent('battery_status', batteryPayload(), { timestamp: '2026-01-01' })
    );
    expect(result.valid).toBe(false);
  });

  test('timestamp with milliseconds passes', () => {
    const result = validateEventEnvelope(
      makeEvent('battery_status', batteryPayload(), { timestamp: '2026-01-01T00:00:00.123Z' })
    );
    expect(result.valid).toBe(true);
  });

  test('array payload fails', () => {
    const result = validateEventEnvelope(makeEvent('battery_status', [] as unknown as Record<string, unknown>));
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field === 'payload')).toBe(true);
  });

  test('optional fields are accepted', () => {
    const result = validateEventEnvelope(makeEvent('battery_status', batteryPayload(), {
      session_id: makeUUID(),
      device_id: 'ev3-001',
      version: '1.0',
      tags: ['robot', 'test'],
      correlation_id: makeUUID(),
    }));
    expect(result.valid).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// validateBatteryStatusPayload
// ---------------------------------------------------------------------------

describe('validateBatteryStatusPayload', () => {
  test('valid minimal payload passes', () => {
    expect(validateBatteryStatusPayload(batteryPayload()).valid).toBe(true);
  });

  test('full valid payload passes', () => {
    const result = validateBatteryStatusPayload({
      voltage_mv: 7200,
      voltage_v: 7.2,
      current_ma: 450,
      percentage: 85,
      battery_type: 'rechargeable',
      is_critical: false,
    });
    expect(result.valid).toBe(true);
  });

  test('missing voltage_mv fails', () => {
    const result = validateBatteryStatusPayload({ percentage: 85 });
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field.includes('voltage_mv'))).toBe(true);
  });

  test('float voltage_mv fails', () => {
    const result = validateBatteryStatusPayload(batteryPayload({ voltage_mv: 7.2 }));
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field.includes('voltage_mv'))).toBe(true);
  });

  test('negative voltage_mv fails', () => {
    expect(validateBatteryStatusPayload(batteryPayload({ voltage_mv: -1 })).valid).toBe(false);
  });

  test('percentage over 100 fails', () => {
    expect(validateBatteryStatusPayload(batteryPayload({ percentage: 101 })).valid).toBe(false);
  });

  test('percentage below 0 fails', () => {
    expect(validateBatteryStatusPayload(batteryPayload({ percentage: -1 })).valid).toBe(false);
  });

  test('invalid battery_type fails', () => {
    expect(validateBatteryStatusPayload(batteryPayload({ battery_type: 'lithium' })).valid).toBe(false);
  });

  test('all valid battery_types pass', () => {
    for (const bt of ['rechargeable', 'alkaline', 'unknown']) {
      expect(validateBatteryStatusPayload(batteryPayload({ battery_type: bt })).valid).toBe(true);
    }
  });

  test('is_critical non-boolean fails', () => {
    expect(validateBatteryStatusPayload(batteryPayload({ is_critical: 'yes' })).valid).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// validateCommandReceivedPayload
// ---------------------------------------------------------------------------

describe('validateCommandReceivedPayload', () => {
  test('valid minimal payload passes', () => {
    expect(validateCommandReceivedPayload(commandReceivedPayload()).valid).toBe(true);
  });

  test('full valid payload passes', () => {
    expect(validateCommandReceivedPayload({
      command: 'forward',
      params: { speed: 500 },
      controller_type: 'ps4',
      received_at_ms: 12345,
    }).valid).toBe(true);
  });

  test('missing command fails', () => {
    const result = validateCommandReceivedPayload({});
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field.includes('command'))).toBe(true);
  });

  test('empty command fails', () => {
    expect(validateCommandReceivedPayload(commandReceivedPayload({ command: '' })).valid).toBe(false);
  });

  test('whitespace-only command fails', () => {
    expect(validateCommandReceivedPayload(commandReceivedPayload({ command: '   ' })).valid).toBe(false);
  });

  test('invalid controller_type fails', () => {
    expect(validateCommandReceivedPayload(commandReceivedPayload({ controller_type: 'gamepad' })).valid).toBe(false);
  });

  test('all valid controller_types pass', () => {
    for (const ct of ['ps4', 'network_remote', 'unknown']) {
      expect(validateCommandReceivedPayload(commandReceivedPayload({ controller_type: ct })).valid).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// validateCommandExecutedPayload
// ---------------------------------------------------------------------------

describe('validateCommandExecutedPayload', () => {
  test('valid payload passes', () => {
    expect(validateCommandExecutedPayload(commandExecutedPayload()).valid).toBe(true);
  });

  test('success=false with error_message passes', () => {
    expect(validateCommandExecutedPayload({
      command: 'forward',
      success: false,
      duration_ms: 50,
      error_message: 'Motor stalled',
    }).valid).toBe(true);
  });

  test('missing command fails', () => {
    expect(validateCommandExecutedPayload({ success: true }).valid).toBe(false);
  });

  test('missing success fails', () => {
    const result = validateCommandExecutedPayload({ command: 'forward' });
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field.includes('success'))).toBe(true);
  });

  test('success as string fails', () => {
    expect(validateCommandExecutedPayload(commandExecutedPayload({ success: 'yes' })).valid).toBe(false);
  });

  test('negative duration_ms fails', () => {
    expect(validateCommandExecutedPayload(commandExecutedPayload({ duration_ms: -1 })).valid).toBe(false);
  });

  test('zero duration_ms passes', () => {
    expect(validateCommandExecutedPayload(commandExecutedPayload({ duration_ms: 0 })).valid).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// validateDeviceStatusPayload
// ---------------------------------------------------------------------------

describe('validateDeviceStatusPayload', () => {
  test('valid minimal payload passes', () => {
    expect(validateDeviceStatusPayload(deviceStatusPayload()).valid).toBe(true);
  });

  test('full valid payload passes', () => {
    expect(validateDeviceStatusPayload({
      device_name: 'drive_L',
      device_type: 'motor',
      port: 'A',
      status: 'connected',
      previous_status: 'disconnected',
    }).valid).toBe(true);
  });

  test('missing device_name fails', () => {
    const result = validateDeviceStatusPayload({ status: 'connected' });
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field.includes('device_name'))).toBe(true);
  });

  test('invalid status fails', () => {
    expect(validateDeviceStatusPayload(deviceStatusPayload({ status: 'broken' })).valid).toBe(false);
  });

  test('all valid statuses pass', () => {
    for (const status of ['connected', 'disconnected', 'error', 'stalled', 'initializing']) {
      expect(validateDeviceStatusPayload(deviceStatusPayload({ status })).valid).toBe(true);
    }
  });

  test('invalid device_type fails', () => {
    expect(validateDeviceStatusPayload(deviceStatusPayload({ device_type: 'antenna' })).valid).toBe(false);
  });

  test('all valid device_types pass', () => {
    for (const dt of ['motor', 'sensor', 'controller', 'unknown']) {
      expect(validateDeviceStatusPayload(deviceStatusPayload({ device_type: dt })).valid).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// validateErrorPayload
// ---------------------------------------------------------------------------

describe('validateErrorPayload', () => {
  test('valid minimal payload passes', () => {
    expect(validateErrorPayload(errorPayload()).valid).toBe(true);
  });

  test('full valid payload passes', () => {
    expect(validateErrorPayload({
      error_type: 'device_error',
      error_code: 'MOTOR_STALL',
      message: 'Left drive motor stalled',
      component: 'DeviceManager',
      stack_trace: 'Traceback...',
      context: { port: 'A' },
    }).valid).toBe(true);
  });

  test('missing error_type fails', () => {
    const result = validateErrorPayload({ message: 'Something went wrong' });
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field.includes('error_type'))).toBe(true);
  });

  test('missing message fails', () => {
    const result = validateErrorPayload({ error_type: 'device_error' });
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field.includes('message'))).toBe(true);
  });

  test('empty error_type fails', () => {
    expect(validateErrorPayload(errorPayload({ error_type: '' })).valid).toBe(false);
  });

  test('whitespace message fails', () => {
    expect(validateErrorPayload(errorPayload({ message: '   ' })).valid).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// validateApiRequestPayload
// ---------------------------------------------------------------------------

describe('validateApiRequestPayload', () => {
  test('valid minimal payload passes', () => {
    expect(validateApiRequestPayload(apiRequestPayload()).valid).toBe(true);
  });

  test('full valid payload passes', () => {
    expect(validateApiRequestPayload({
      endpoint: 'controlRobot',
      method: 'POST',
      command: 'forward',
      status_code: 200,
      latency_ms: 150,
      robot_response_time_ms: 120,
      client_ip_hash: 'abc123',
    }).valid).toBe(true);
  });

  test('missing endpoint fails', () => {
    const result = validateApiRequestPayload({ status_code: 200, latency_ms: 100 });
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field.includes('endpoint'))).toBe(true);
  });

  test('missing status_code fails', () => {
    const result = validateApiRequestPayload({ endpoint: 'controlRobot', latency_ms: 100 });
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field.includes('status_code'))).toBe(true);
  });

  test('status_code 99 fails', () => {
    expect(validateApiRequestPayload(apiRequestPayload({ status_code: 99 })).valid).toBe(false);
  });

  test('status_code 600 fails', () => {
    expect(validateApiRequestPayload(apiRequestPayload({ status_code: 600 })).valid).toBe(false);
  });

  test('float status_code fails', () => {
    expect(validateApiRequestPayload(apiRequestPayload({ status_code: 200.5 })).valid).toBe(false);
  });

  test('negative latency_ms fails', () => {
    expect(validateApiRequestPayload(apiRequestPayload({ latency_ms: -1 })).valid).toBe(false);
  });

  test('invalid method fails', () => {
    expect(validateApiRequestPayload(apiRequestPayload({ method: 'CONNECT' })).valid).toBe(false);
  });

  test('all valid HTTP methods pass', () => {
    for (const method of ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']) {
      expect(validateApiRequestPayload(apiRequestPayload({ method })).valid).toBe(true);
    }
  });

  test('4xx and 5xx status codes are valid', () => {
    for (const code of [400, 401, 403, 404, 500, 502, 503]) {
      expect(validateApiRequestPayload(apiRequestPayload({ status_code: code })).valid).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// validateTelemetryEvent (full event)
// ---------------------------------------------------------------------------

describe('validateTelemetryEvent', () => {
  test('valid battery_status event passes', () => {
    const result = validateTelemetryEvent(makeEvent('battery_status', batteryPayload()));
    expect(result.valid).toBe(true);
  });

  test('valid command_received event passes', () => {
    expect(validateTelemetryEvent(makeEvent('command_received', commandReceivedPayload())).valid).toBe(true);
  });

  test('valid command_executed event passes', () => {
    expect(validateTelemetryEvent(makeEvent('command_executed', commandExecutedPayload())).valid).toBe(true);
  });

  test('valid device_status event passes', () => {
    expect(validateTelemetryEvent(makeEvent('device_status', deviceStatusPayload())).valid).toBe(true);
  });

  test('valid error event passes', () => {
    expect(validateTelemetryEvent(makeEvent('error', errorPayload())).valid).toBe(true);
  });

  test('valid api_request event passes', () => {
    expect(validateTelemetryEvent(makeEvent('api_request', apiRequestPayload(), { source: 'cloud_functions' })).valid).toBe(true);
  });

  test('event with invalid envelope fails at envelope stage', () => {
    const result = validateTelemetryEvent({ event_type: 'battery_status' });
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field === 'event_id')).toBe(true);
  });

  test('event with invalid payload fails at payload stage', () => {
    const result = validateTelemetryEvent(makeEvent('battery_status', { percentage: 85 }));
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.field.includes('voltage_mv'))).toBe(true);
  });

  test('non-P0 event type with empty payload passes (no payload validator)', () => {
    const result = validateTelemetryEvent(makeEvent('motor_status', {}));
    expect(result.valid).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// validateTelemetryEventBatch
// ---------------------------------------------------------------------------

describe('validateTelemetryEventBatch', () => {
  test('empty batch returns empty array', () => {
    expect(validateTelemetryEventBatch([])).toHaveLength(0);
  });

  test('all valid events returns all valid', () => {
    const events = [
      makeEvent('battery_status', batteryPayload()),
      makeEvent('command_received', commandReceivedPayload()),
    ];
    const results = validateTelemetryEventBatch(events);
    expect(results).toHaveLength(2);
    expect(results.every(r => r.valid)).toBe(true);
  });

  test('mixed valid/invalid events returns correct statuses', () => {
    const events = [
      makeEvent('battery_status', batteryPayload()),
      { event_type: 'unknown_event' },
    ];
    const results = validateTelemetryEventBatch(events);
    expect(results[0].valid).toBe(true);
    expect(results[0].index).toBe(0);
    expect(results[1].valid).toBe(false);
    expect(results[1].index).toBe(1);
  });

  test('preserves index in results', () => {
    const events = [
      { event_type: 'bad' },
      makeEvent('battery_status', batteryPayload()),
      { event_type: 'also_bad' },
    ];
    const results = validateTelemetryEventBatch(events);
    expect(results[0].index).toBe(0);
    expect(results[1].index).toBe(1);
    expect(results[2].index).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// isValidTelemetryEvent
// ---------------------------------------------------------------------------

describe('isValidTelemetryEvent', () => {
  test('returns true for valid event', () => {
    expect(isValidTelemetryEvent(makeEvent('battery_status', batteryPayload()))).toBe(true);
  });

  test('returns false for invalid event', () => {
    expect(isValidTelemetryEvent({ event_type: 'bad' })).toBe(false);
  });

  test('returns false for null', () => {
    expect(isValidTelemetryEvent(null)).toBe(false);
  });
});
