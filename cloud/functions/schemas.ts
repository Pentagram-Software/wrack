/**
 * Wrack Telemetry — TypeScript event schema validation for Cloud Functions.
 *
 * This module implements runtime validation of telemetry events against the
 * canonical schemas defined in `shared/telemetry-types/schemas/`.
 *
 * It re-exports the shared TypeScript types from `shared/telemetry-types/`
 * and adds Cloud-Function-specific helpers (batch validation, error formatting).
 *
 * Usage:
 *   const { valid, errors } = validateTelemetryEvent(rawEvent);
 *   if (!valid) { return res.status(400).json({ errors }); }
 */

// ---------------------------------------------------------------------------
// Types (mirrored from shared/telemetry-types/typescript/events.ts)
// ---------------------------------------------------------------------------

export type EventSource = 'ev3' | 'rpi' | 'cloud_functions' | 'web' | 'ios';

export type EventType =
  | 'battery_status'
  | 'command_received'
  | 'command_executed'
  | 'device_status'
  | 'error'
  | 'api_request'
  | 'motor_status'
  | 'sensor_reading'
  | 'terrain_scan'
  | 'connection_status';

export interface TelemetryEventEnvelope {
  event_id: string;
  event_type: EventType;
  source: EventSource;
  timestamp: string;
  payload: Record<string, unknown>;
  session_id?: string | null;
  device_id?: string | null;
  version?: string | null;
  tags?: string[] | null;
  user_id?: string | null;
  correlation_id?: string | null;
}

export type BatteryType = 'rechargeable' | 'alkaline' | 'unknown';

export interface BatteryStatusPayload {
  voltage_mv: number;
  voltage_v?: number;
  current_ma?: number;
  percentage: number;
  battery_type?: BatteryType;
  is_critical?: boolean;
}

export type ControllerType = 'ps4' | 'network_remote' | 'unknown';

export interface CommandReceivedPayload {
  command: string;
  params?: Record<string, unknown> | null;
  controller_type?: ControllerType;
  received_at_ms?: number;
}

export interface CommandExecutedPayload {
  command: string;
  success: boolean;
  duration_ms?: number;
  error_message?: string | null;
  params?: Record<string, unknown> | null;
  controller_type?: ControllerType;
}

export type DeviceStatusValue =
  | 'connected'
  | 'disconnected'
  | 'error'
  | 'stalled'
  | 'initializing';

export type DeviceType = 'motor' | 'sensor' | 'controller' | 'unknown';

export interface DeviceStatusPayload {
  device_name: string;
  device_type?: DeviceType;
  port?: string | null;
  status: DeviceStatusValue;
  previous_status?: DeviceStatusValue | 'unknown' | null;
  error_message?: string | null;
}

export interface ErrorPayload {
  error_type: string;
  error_code?: string | null;
  message: string;
  component?: string | null;
  stack_trace?: string | null;
  context?: Record<string, unknown> | null;
}

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'OPTIONS';

export interface ApiRequestPayload {
  endpoint: string;
  method?: HttpMethod;
  command?: string | null;
  status_code: number;
  latency_ms: number;
  robot_response_time_ms?: number | null;
  client_ip_hash?: string | null;
  error_message?: string | null;
}

// ---------------------------------------------------------------------------
// Validation infrastructure
// ---------------------------------------------------------------------------

export interface ValidationError {
  field: string;
  message: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const VALID_SOURCES: readonly EventSource[] = [
  'ev3', 'rpi', 'cloud_functions', 'web', 'ios',
] as const;

export const VALID_EVENT_TYPES: readonly EventType[] = [
  'battery_status', 'command_received', 'command_executed',
  'device_status', 'error', 'api_request',
  'motor_status', 'sensor_reading', 'terrain_scan', 'connection_status',
] as const;

export const P0_EVENT_TYPES: readonly EventType[] = [
  'battery_status', 'command_received', 'command_executed',
  'device_status', 'error', 'api_request',
] as const;

const VALID_DEVICE_STATUSES: readonly DeviceStatusValue[] = [
  'connected', 'disconnected', 'error', 'stalled', 'initializing',
] as const;

const VALID_DEVICE_TYPES: readonly DeviceType[] = [
  'motor', 'sensor', 'controller', 'unknown',
] as const;

const VALID_BATTERY_TYPES: readonly BatteryType[] = [
  'rechargeable', 'alkaline', 'unknown',
] as const;

const VALID_CONTROLLER_TYPES: readonly ControllerType[] = [
  'ps4', 'network_remote', 'unknown',
] as const;

const VALID_HTTP_METHODS: readonly HttpMethod[] = [
  'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS',
] as const;

const ISO_8601_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// ---------------------------------------------------------------------------
// Envelope validation
// ---------------------------------------------------------------------------

/**
 * Validates the common event envelope fields.
 * Does NOT validate the `payload` — use {@link validateTelemetryEvent} for that.
 */
export function validateEventEnvelope(event: unknown): ValidationResult {
  const errors: ValidationError[] = [];

  if (typeof event !== 'object' || event === null) {
    return {
      valid: false,
      errors: [{ field: 'root', message: 'Event must be a non-null object' }],
    };
  }

  const e = event as Record<string, unknown>;

  if (typeof e.event_id !== 'string' || !UUID_RE.test(e.event_id)) {
    errors.push({ field: 'event_id', message: 'Must be a valid UUID v4 string' });
  }

  if (
    typeof e.event_type !== 'string' ||
    !(VALID_EVENT_TYPES as readonly string[]).includes(e.event_type)
  ) {
    errors.push({
      field: 'event_type',
      message: `Must be one of: ${VALID_EVENT_TYPES.join(', ')}`,
    });
  }

  if (
    typeof e.source !== 'string' ||
    !(VALID_SOURCES as readonly string[]).includes(e.source)
  ) {
    errors.push({
      field: 'source',
      message: `Must be one of: ${VALID_SOURCES.join(', ')}`,
    });
  }

  if (typeof e.timestamp !== 'string' || !ISO_8601_RE.test(e.timestamp)) {
    errors.push({
      field: 'timestamp',
      message:
        'Must be an ISO 8601 UTC timestamp string ending in Z (e.g. 2026-01-01T00:00:00Z)',
    });
  }

  if (
    typeof e.payload !== 'object' ||
    e.payload === null ||
    Array.isArray(e.payload)
  ) {
    errors.push({ field: 'payload', message: 'Must be a non-null object' });
  }

  return { valid: errors.length === 0, errors };
}

// ---------------------------------------------------------------------------
// Payload validators
// ---------------------------------------------------------------------------

/** Validates a `battery_status` payload. */
export function validateBatteryStatusPayload(payload: unknown): ValidationResult {
  const errors: ValidationError[] = [];
  if (typeof payload !== 'object' || payload === null) {
    return { valid: false, errors: [{ field: 'payload', message: 'Must be a non-null object' }] };
  }
  const p = payload as Record<string, unknown>;

  if (
    typeof p.voltage_mv !== 'number' ||
    !Number.isInteger(p.voltage_mv) ||
    p.voltage_mv < 0
  ) {
    errors.push({ field: 'payload.voltage_mv', message: 'Must be a non-negative integer' });
  }

  if (
    typeof p.percentage !== 'number' ||
    p.percentage < 0 ||
    p.percentage > 100
  ) {
    errors.push({ field: 'payload.percentage', message: 'Must be a number between 0 and 100' });
  }

  if (p.voltage_v !== undefined && p.voltage_v !== null) {
    if (typeof p.voltage_v !== 'number' || p.voltage_v < 0) {
      errors.push({ field: 'payload.voltage_v', message: 'Must be a non-negative number' });
    }
  }

  if (p.is_critical !== undefined && p.is_critical !== null) {
    if (typeof p.is_critical !== 'boolean') {
      errors.push({ field: 'payload.is_critical', message: 'Must be a boolean' });
    }
  }

  if (p.battery_type !== undefined && p.battery_type !== null) {
    if (!(VALID_BATTERY_TYPES as readonly string[]).includes(p.battery_type as string)) {
      errors.push({
        field: 'payload.battery_type',
        message: `Must be one of: ${VALID_BATTERY_TYPES.join(', ')}`,
      });
    }
  }

  return { valid: errors.length === 0, errors };
}

/** Validates a `command_received` payload. */
export function validateCommandReceivedPayload(payload: unknown): ValidationResult {
  const errors: ValidationError[] = [];
  if (typeof payload !== 'object' || payload === null) {
    return { valid: false, errors: [{ field: 'payload', message: 'Must be a non-null object' }] };
  }
  const p = payload as Record<string, unknown>;

  if (typeof p.command !== 'string' || p.command.trim() === '') {
    errors.push({ field: 'payload.command', message: 'Must be a non-empty string' });
  }

  if (p.controller_type !== undefined && p.controller_type !== null) {
    if (!(VALID_CONTROLLER_TYPES as readonly string[]).includes(p.controller_type as string)) {
      errors.push({
        field: 'payload.controller_type',
        message: `Must be one of: ${VALID_CONTROLLER_TYPES.join(', ')}`,
      });
    }
  }

  return { valid: errors.length === 0, errors };
}

/** Validates a `command_executed` payload. */
export function validateCommandExecutedPayload(payload: unknown): ValidationResult {
  const errors: ValidationError[] = [];
  if (typeof payload !== 'object' || payload === null) {
    return { valid: false, errors: [{ field: 'payload', message: 'Must be a non-null object' }] };
  }
  const p = payload as Record<string, unknown>;

  if (typeof p.command !== 'string' || p.command.trim() === '') {
    errors.push({ field: 'payload.command', message: 'Must be a non-empty string' });
  }

  if (typeof p.success !== 'boolean') {
    errors.push({ field: 'payload.success', message: 'Must be a boolean' });
  }

  if (p.duration_ms !== undefined && p.duration_ms !== null) {
    if (typeof p.duration_ms !== 'number' || p.duration_ms < 0) {
      errors.push({ field: 'payload.duration_ms', message: 'Must be a non-negative number' });
    }
  }

  return { valid: errors.length === 0, errors };
}

/** Validates a `device_status` payload. */
export function validateDeviceStatusPayload(payload: unknown): ValidationResult {
  const errors: ValidationError[] = [];
  if (typeof payload !== 'object' || payload === null) {
    return { valid: false, errors: [{ field: 'payload', message: 'Must be a non-null object' }] };
  }
  const p = payload as Record<string, unknown>;

  if (typeof p.device_name !== 'string' || p.device_name.trim() === '') {
    errors.push({ field: 'payload.device_name', message: 'Must be a non-empty string' });
  }

  if (
    typeof p.status !== 'string' ||
    !(VALID_DEVICE_STATUSES as readonly string[]).includes(p.status)
  ) {
    errors.push({
      field: 'payload.status',
      message: `Must be one of: ${VALID_DEVICE_STATUSES.join(', ')}`,
    });
  }

  if (p.device_type !== undefined && p.device_type !== null) {
    if (!(VALID_DEVICE_TYPES as readonly string[]).includes(p.device_type as string)) {
      errors.push({
        field: 'payload.device_type',
        message: `Must be one of: ${VALID_DEVICE_TYPES.join(', ')}`,
      });
    }
  }

  return { valid: errors.length === 0, errors };
}

/** Validates an `error` payload. */
export function validateErrorPayload(payload: unknown): ValidationResult {
  const errors: ValidationError[] = [];
  if (typeof payload !== 'object' || payload === null) {
    return { valid: false, errors: [{ field: 'payload', message: 'Must be a non-null object' }] };
  }
  const p = payload as Record<string, unknown>;

  if (typeof p.error_type !== 'string' || p.error_type.trim() === '') {
    errors.push({ field: 'payload.error_type', message: 'Must be a non-empty string' });
  }

  if (typeof p.message !== 'string' || p.message.trim() === '') {
    errors.push({ field: 'payload.message', message: 'Must be a non-empty string' });
  }

  return { valid: errors.length === 0, errors };
}

/** Validates an `api_request` payload. */
export function validateApiRequestPayload(payload: unknown): ValidationResult {
  const errors: ValidationError[] = [];
  if (typeof payload !== 'object' || payload === null) {
    return { valid: false, errors: [{ field: 'payload', message: 'Must be a non-null object' }] };
  }
  const p = payload as Record<string, unknown>;

  if (typeof p.endpoint !== 'string' || p.endpoint.trim() === '') {
    errors.push({ field: 'payload.endpoint', message: 'Must be a non-empty string' });
  }

  if (
    typeof p.status_code !== 'number' ||
    !Number.isInteger(p.status_code) ||
    p.status_code < 100 ||
    p.status_code > 599
  ) {
    errors.push({
      field: 'payload.status_code',
      message: 'Must be an integer HTTP status code (100–599)',
    });
  }

  if (typeof p.latency_ms !== 'number' || p.latency_ms < 0) {
    errors.push({ field: 'payload.latency_ms', message: 'Must be a non-negative number' });
  }

  if (p.method !== undefined && p.method !== null) {
    if (!(VALID_HTTP_METHODS as readonly string[]).includes(p.method as string)) {
      errors.push({
        field: 'payload.method',
        message: `Must be one of: ${VALID_HTTP_METHODS.join(', ')}`,
      });
    }
  }

  return { valid: errors.length === 0, errors };
}

// ---------------------------------------------------------------------------
// Dispatch table
// ---------------------------------------------------------------------------

type PayloadValidator = (payload: unknown) => ValidationResult;

const PAYLOAD_VALIDATORS: Partial<Record<EventType, PayloadValidator>> = {
  battery_status: validateBatteryStatusPayload,
  command_received: validateCommandReceivedPayload,
  command_executed: validateCommandExecutedPayload,
  device_status: validateDeviceStatusPayload,
  error: validateErrorPayload,
  api_request: validateApiRequestPayload,
};

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Validates the full event (envelope + payload).
 *
 * @param event - Raw untrusted object from a request body.
 * @returns `{ valid, errors }` where errors is an array of `{ field, message }`.
 */
export function validateTelemetryEvent(event: unknown): ValidationResult {
  const envelopeResult = validateEventEnvelope(event);
  if (!envelopeResult.valid) {
    return envelopeResult;
  }

  const e = event as TelemetryEventEnvelope;
  const payloadValidator = PAYLOAD_VALIDATORS[e.event_type];
  if (!payloadValidator) {
    return { valid: true, errors: [] };
  }

  return payloadValidator(e.payload);
}

/**
 * Validates a batch of events.
 *
 * @param events - Array of raw untrusted objects.
 * @returns Array of `{ index, valid, errors }` for each event.
 */
export function validateTelemetryEventBatch(
  events: unknown[],
): Array<{ index: number; valid: boolean; errors: ValidationError[] }> {
  return events.map((event, index) => ({
    index,
    ...validateTelemetryEvent(event),
  }));
}

/**
 * Convenience guard: returns true if the event is fully valid.
 */
export function isValidTelemetryEvent(event: unknown): event is TelemetryEventEnvelope {
  return validateTelemetryEvent(event).valid;
}
