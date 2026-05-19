/**
 * Wrack Telemetry — Shared TypeScript event types and validation helpers.
 *
 * These types mirror the canonical JSON Schema definitions in
 * `shared/telemetry-types/schemas/`. Keep them in sync when schemas evolve.
 *
 * Usage:
 *   import { TelemetryEvent, EventType, validateEventEnvelope } from './events';
 */

// ---------------------------------------------------------------------------
// Common envelope
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

/** Common envelope shared by every telemetry event. */
export interface TelemetryEventEnvelope {
  event_id: string;
  event_type: EventType;
  source: EventSource;
  /** ISO 8601 UTC timestamp of when the event occurred at the source. */
  timestamp: string;
  session_id?: string | null;
  device_id?: string | null;
  payload: Record<string, unknown>;
  version?: string | null;
  tags?: string[] | null;
  user_id?: string | null;
  correlation_id?: string | null;
}

// ---------------------------------------------------------------------------
// P0 payload types
// ---------------------------------------------------------------------------

export type BatteryType = 'rechargeable' | 'alkaline' | 'unknown';

/** Payload for `battery_status` events. */
export interface BatteryStatusPayload {
  /** Battery voltage in millivolts. */
  voltage_mv: number;
  /** Battery voltage in volts. */
  voltage_v?: number;
  /** Battery current draw in milliamps. */
  current_ma?: number;
  /** Estimated remaining charge 0–100. */
  percentage: number;
  battery_type?: BatteryType;
  /** True when voltage is below the low-battery threshold. */
  is_critical?: boolean;
}

export type ControllerType = 'ps4' | 'network_remote' | 'unknown';

/** Payload for `command_received` events. */
export interface CommandReceivedPayload {
  command: string;
  params?: Record<string, unknown> | null;
  controller_type?: ControllerType;
  received_at_ms?: number;
}

/** Payload for `command_executed` events. */
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

/** Payload for `device_status` events. */
export interface DeviceStatusPayload {
  device_name: string;
  device_type?: DeviceType;
  port?: string | null;
  status: DeviceStatusValue;
  previous_status?: DeviceStatusValue | 'unknown' | null;
  error_message?: string | null;
}

/** Payload for `error` events. */
export interface ErrorPayload {
  error_type: string;
  error_code?: string | null;
  message: string;
  component?: string | null;
  stack_trace?: string | null;
  context?: Record<string, unknown> | null;
}

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'OPTIONS';

/** Payload for `api_request` events. */
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
// Discriminated union — typed event wrappers
// ---------------------------------------------------------------------------

export type BatteryStatusEvent = TelemetryEventEnvelope & {
  event_type: 'battery_status';
  payload: BatteryStatusPayload;
};

export type CommandReceivedEvent = TelemetryEventEnvelope & {
  event_type: 'command_received';
  payload: CommandReceivedPayload;
};

export type CommandExecutedEvent = TelemetryEventEnvelope & {
  event_type: 'command_executed';
  payload: CommandExecutedPayload;
};

export type DeviceStatusEvent = TelemetryEventEnvelope & {
  event_type: 'device_status';
  payload: DeviceStatusPayload;
};

export type ErrorEvent = TelemetryEventEnvelope & {
  event_type: 'error';
  payload: ErrorPayload;
};

export type ApiRequestEvent = TelemetryEventEnvelope & {
  event_type: 'api_request';
  payload: ApiRequestPayload;
};

/** Union of all typed telemetry events. */
export type TelemetryEvent =
  | BatteryStatusEvent
  | CommandReceivedEvent
  | CommandExecutedEvent
  | DeviceStatusEvent
  | ErrorEvent
  | ApiRequestEvent;

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

/** Errors collected during validation. */
export interface ValidationError {
  field: string;
  message: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
}

const VALID_SOURCES: readonly EventSource[] = [
  'ev3', 'rpi', 'cloud_functions', 'web', 'ios',
] as const;

const VALID_EVENT_TYPES: readonly EventType[] = [
  'battery_status', 'command_received', 'command_executed',
  'device_status', 'error', 'api_request',
  'motor_status', 'sensor_reading', 'terrain_scan', 'connection_status',
] as const;

const ISO_8601_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Validates the common event envelope fields.
 * Does NOT validate the `payload` — call the type-specific validator for that.
 */
export function validateEventEnvelope(
  event: unknown,
): ValidationResult {
  const errors: ValidationError[] = [];

  if (typeof event !== 'object' || event === null) {
    return { valid: false, errors: [{ field: 'root', message: 'Event must be a non-null object' }] };
  }

  const e = event as Record<string, unknown>;

  if (typeof e.event_id !== 'string' || !UUID_RE.test(e.event_id)) {
    errors.push({ field: 'event_id', message: 'Must be a valid UUID v4 string' });
  }

  if (typeof e.event_type !== 'string' || !(VALID_EVENT_TYPES as readonly string[]).includes(e.event_type)) {
    errors.push({
      field: 'event_type',
      message: `Must be one of: ${VALID_EVENT_TYPES.join(', ')}`,
    });
  }

  if (typeof e.source !== 'string' || !(VALID_SOURCES as readonly string[]).includes(e.source)) {
    errors.push({
      field: 'source',
      message: `Must be one of: ${VALID_SOURCES.join(', ')}`,
    });
  }

  if (typeof e.timestamp !== 'string' || !ISO_8601_RE.test(e.timestamp)) {
    errors.push({
      field: 'timestamp',
      message: 'Must be an ISO 8601 UTC timestamp string ending in Z (e.g. 2026-01-01T00:00:00Z)',
    });
  }

  if (typeof e.payload !== 'object' || e.payload === null || Array.isArray(e.payload)) {
    errors.push({ field: 'payload', message: 'Must be a non-null object' });
  }

  return { valid: errors.length === 0, errors };
}

/** Validates a `battery_status` payload. */
export function validateBatteryStatusPayload(payload: unknown): ValidationResult {
  const errors: ValidationError[] = [];
  if (typeof payload !== 'object' || payload === null) {
    return { valid: false, errors: [{ field: 'payload', message: 'Must be a non-null object' }] };
  }
  const p = payload as Record<string, unknown>;

  if (typeof p.voltage_mv !== 'number' || !Number.isInteger(p.voltage_mv) || p.voltage_mv < 0) {
    errors.push({ field: 'payload.voltage_mv', message: 'Must be a non-negative integer' });
  }
  if (typeof p.percentage !== 'number' || p.percentage < 0 || p.percentage > 100) {
    errors.push({ field: 'payload.percentage', message: 'Must be a number between 0 and 100' });
  }
  if (p.voltage_v !== undefined && p.voltage_v !== null && (typeof p.voltage_v !== 'number' || p.voltage_v < 0)) {
    errors.push({ field: 'payload.voltage_v', message: 'Must be a non-negative number' });
  }
  if (p.is_critical !== undefined && p.is_critical !== null && typeof p.is_critical !== 'boolean') {
    errors.push({ field: 'payload.is_critical', message: 'Must be a boolean' });
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
  if (p.duration_ms !== undefined && p.duration_ms !== null &&
      (typeof p.duration_ms !== 'number' || p.duration_ms < 0)) {
    errors.push({ field: 'payload.duration_ms', message: 'Must be a non-negative number' });
  }

  return { valid: errors.length === 0, errors };
}

const VALID_DEVICE_STATUSES = ['connected', 'disconnected', 'error', 'stalled', 'initializing'] as const;

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
  if (typeof p.status !== 'string' || !(VALID_DEVICE_STATUSES as readonly string[]).includes(p.status)) {
    errors.push({
      field: 'payload.status',
      message: `Must be one of: ${VALID_DEVICE_STATUSES.join(', ')}`,
    });
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
  if (typeof p.status_code !== 'number' || !Number.isInteger(p.status_code) ||
      p.status_code < 100 || p.status_code > 599) {
    errors.push({ field: 'payload.status_code', message: 'Must be an integer HTTP status code (100–599)' });
  }
  if (typeof p.latency_ms !== 'number' || p.latency_ms < 0) {
    errors.push({ field: 'payload.latency_ms', message: 'Must be a non-negative number' });
  }

  return { valid: errors.length === 0, errors };
}

// ---------------------------------------------------------------------------
// Convenience: validate envelope + payload together
// ---------------------------------------------------------------------------

const PAYLOAD_VALIDATORS: Partial<Record<EventType, (p: unknown) => ValidationResult>> = {
  battery_status: validateBatteryStatusPayload,
  command_received: validateCommandReceivedPayload,
  command_executed: validateCommandExecutedPayload,
  device_status: validateDeviceStatusPayload,
  error: validateErrorPayload,
  api_request: validateApiRequestPayload,
};

/**
 * Validates the full event (envelope + payload).
 * Errors from both layers are merged into a single result.
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

  const payloadResult = payloadValidator(e.payload);
  return {
    valid: payloadResult.valid,
    errors: payloadResult.errors,
  };
}
