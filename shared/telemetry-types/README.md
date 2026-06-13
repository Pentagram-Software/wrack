# shared/telemetry-types

Shared telemetry event type definitions and JSON Schemas for the Wrack robot system.

This package is the **single source of truth** for event contracts across all Wrack components. Changes here must be reflected in both the EV3 Python module and the Cloud Functions TypeScript module.

## Directory layout

```
shared/telemetry-types/
├── schemas/                    # Canonical JSON Schema files (Draft-07)
│   ├── event_envelope.json     # Common envelope (all events)
│   ├── battery_status.json     # EV3 battery payload
│   ├── command_received.json   # EV3 command-received payload
│   ├── command_executed.json   # EV3 command-executed payload
│   ├── device_status.json      # EV3 device connect/disconnect payload
│   ├── error.json              # Error event payload (all sources)
│   └── api_request.json        # Cloud Function API request payload
├── typescript/
│   └── events.ts               # TypeScript types + validation helpers
└── python/
    └── events.py               # Python type aliases + constants
```

## Event envelope

Every telemetry event shares the same top-level structure:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_id` | UUID string | ✓ | Unique event identifier |
| `event_type` | enum string | ✓ | Discriminator (see below) |
| `source` | enum string | ✓ | `ev3`, `rpi`, `cloud_functions`, `web`, `ios` |
| `timestamp` | ISO 8601 UTC string | ✓ | Event creation time at source |
| `payload` | object | ✓ | Event-type-specific data |
| `session_id` | string | | UUID grouping events in a session |
| `device_id` | string | | Physical device identifier |
| `version` | string | | Schema version (e.g. `"1.0"`) |
| `tags` | string[] | | Arbitrary grouping tags |
| `user_id` | string | | User identifier (no PII) |
| `correlation_id` | string | | Cross-component tracing ID |

## P0 event types

| `event_type` | Source | Trigger | Key payload fields |
|---|---|---|---|
| `battery_status` | EV3 | Every 60 s | `voltage_mv`, `percentage` |
| `command_received` | EV3 | On command arrival | `command`, `controller_type` |
| `command_executed` | EV3 | After motor action | `command`, `success`, `duration_ms` |
| `device_status` | EV3 | Device connect/disconnect | `device_name`, `status` |
| `error` | Any | On exception / error | `error_type`, `message` |
| `api_request` | Cloud Functions | Every HTTP request | `endpoint`, `status_code`, `latency_ms` |

## TypeScript usage

```typescript
import {
  TelemetryEvent,
  validateTelemetryEvent,
  validateEventEnvelope,
} from './typescript/events';

const result = validateTelemetryEvent(rawEvent);
if (!result.valid) {
  console.error(result.errors);
}
```

### Web client — TelemetrySender

The web client (`clients/web/src/lib/telemetry-sender.ts`) provides a higher-level
`TelemetrySender` class that batches events and sends them to the `telemetryIngestion`
Cloud Function:

```typescript
import { telemetrySender } from '@/lib/telemetry-sender';
import type { TelemetryEventEnvelope } from '@/lib/telemetry-sender';

// Track an event — it will be batched and flushed automatically
telemetrySender.track({
  event_id: crypto.randomUUID(),
  event_type: 'device_status',
  source: 'web',
  timestamp: new Date().toISOString(),
  payload: { device_name: 'browser', status: 'connected' },
});

// Flush immediately (e.g. before page unload)
await telemetrySender.flush();
```

Key behaviours:
- Batches up to **100 events** per HTTP request
- **Exponential backoff** with 3 retries (delays: 1 s, 2 s, 4 s)
- **Offline graceful degradation**: batches are dropped when `navigator.onLine === false`
- **Non-blocking**: errors are logged but never thrown to callers
- **Background flush** every 30 s for low-traffic scenarios

Required env var: `NEXT_PUBLIC_TELEMETRY_FUNCTION_URL`

## Python usage

```python
from shared.telemetry_types.python.events import (
    VALID_EVENT_TYPES,
    VALID_SOURCES,
    P0_EVENT_TYPES,
)
```

For runtime validation use `robot/controller/telemetry/schemas.py`:

```python
from robot.controller.telemetry.schemas import validate_event, ValidationError

try:
    validate_event(event_dict)
except ValidationError as exc:
    print(exc.errors)
```

## Schema evolution

1. Update the relevant `schemas/*.json` file.
2. Update `typescript/events.ts` types and validators.
3. Update `python/events.py` constants if enum values changed.
4. Bump `version` in new events to `"1.1"` (or next minor).
5. Update `robot/controller/telemetry/schemas.py` and `cloud/functions/schemas.ts`.
6. Add a migration note to `cloud/bigquery/migrations/` if the BigQuery schema changes.
