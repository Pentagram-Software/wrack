# AGENTS.md

## Project overview
- EV3 robot controlled by a PS4 controller using Pybricks.
- Hardware access goes through `DeviceManager` for safe/optional device handling.
- Local development can run without an EV3 by keeping hardware calls mocked or guarded.

## Module structure

| Module | Purpose |
|--------|---------|
| `event_handler/` | Base event pub/sub mixin (`EventHandler`). |
| `robot_controllers/` | PS4 + TCP network remote control. |
| `ev3_devices/` | Device abstraction (`DeviceManager`, drive systems, turret, hot-plug). |
| `wake_word/` | Mycroft Precise "Hey Wrack" wake-word detection. |
| `error_reporting/` | MicroPython-safe structured error logging. |
| `telemetry/` | Event collection, buffering, and HTTP sending to GCP Cloud Functions. |
| `pixy_camera/` | Pixy2 vision camera wrapper. |

### EventHandler telemetry integration

`EventHandler.trigger()` automatically emits two telemetry events per call when a collector is attached:

1. **`command_received`** — emitted *before* callbacks run; includes `controller_type` derived from the class-level `_controller_type` attribute.
2. **`command_executed`** — emitted *after* all callbacks complete; includes `success` (bool), `duration_ms` (wall-clock callback time), `controller_type`, and `error_message` if a callback raised.

Subclasses declare their controller type:

| Class | `_controller_type` |
|-------|--------------------|
| `EventHandler` (base) | `"unknown"` |
| `PS4Controller` | `"ps4"` |
| `RemoteController` | `"network_remote"` |

Collector exceptions are always swallowed so telemetry never breaks the control path. Callback exceptions are re-raised **after** `command_executed` has been emitted (with `success=False`).

### Telemetry module (`telemetry/`)

The telemetry module provides a non-blocking pipeline for forwarding robot events to BigQuery via a GCP Cloud Function.

| File | Role |
|------|------|
| `telemetry/__init__.py` | Public API — re-exports `TelemetryCollector`, `TelemetrySender`, and schema helpers. |
| `telemetry/schemas.py` | Pure-Python event validation (MicroPython-compatible). |
| `telemetry/collector.py` | Builds and buffers telemetry event envelopes; persists overflow to disk. |
| `telemetry/sender.py` | HTTP POST to Cloud Function with batching and exponential back-off retry. |
| `telemetry/tests/` | Unit tests for all three modules. |

**Quick start:**
```python
from telemetry import TelemetryCollector, TelemetrySender

collector = TelemetryCollector(source="ev3")
sender = TelemetrySender(
    endpoint="https://<region>-<project>.cloudfunctions.net/telemetryIngestion",
    api_key="<api-key>",
)

collector.collect_battery_status(voltage_mv=7500, percentage=90.0)
sender.flush_and_send(collector)          # blocking
# or: sender.flush_and_send(collector, async_send=True)  # fire-and-forget
```

Environment variables used by the sender (read by the caller — not auto-read by the module):
- `TELEMETRY_ENDPOINT` — Cloud Function URL.
- `TELEMETRY_API_KEY` — API key for the `X-API-Key` header.

## Setup commands
- Python 3.10+ recommended.
- python -m venv .venv
- source .venv/bin/activate
- pip install -r requirements-test.txt

## Dev environment tips
- Keep hardware-specific imports/usage behind guards so code can run on a laptop.
- Prefer dependency injection for sensors/motors to simplify mocking in tests.
- Use `pytest -q` for quick feedback; full run uses coverage and writes to `htmlcov/`.
- When iterating on EV3 code, commit small changes and keep logs concise for on-brick debugging.

## Testing instructions
- Run from repo root: `pytest`
  - Uses settings in `pytest.ini`; coverage reports to `htmlcov/` and XML.
- To target a subset: `pytest tests/test_<area>.py -k "<pattern>"`.
- If hardware is unavailable, mock device classes to avoid import/runtime errors.
- Keep coverage healthy; add/adjust tests when touching controllers, device manager, or safety logic.
- Telemetry-specific tests: `pytest telemetry/tests/ event_handler/tests/ -q`
- **MicroPython compatibility check (PEN-220):** `python3 scripts/build_mpy_cross.py && python3 scripts/check_mpy_compat.py`
  (or `make check-mpy` from the repo root) compiles every file that ships to the EV3 with the real
  MicroPython cross-compiler, pinned to the exact MicroPython version (v1.11) the EV3's frozen
  Pybricks firmware uses. It's a syntax-only check — see the repo root `CLAUDE.md`'s "MicroPython
  compatibility" section for exactly what it does and doesn't catch. Also runs in `ci-robot.yml` and
  as a pre-deploy gate in `deploy-robot.yml`. First run builds and caches mpy-cross (needs `git` +
  a C compiler on `PATH`); subsequent runs reuse the cached binary.

## Telemetry module (`telemetry/`)

| File | Role |
|------|------|
| `schemas.py` | Pure-Python + optional jsonschema validation for all event types |
| `collector.py` | Thread-safe in-memory event buffer (`TelemetryCollector`) |
| `sender.py` | HTTP delivery to Cloud Function endpoint (`TelemetrySender`) |
| `status_collector.py` | Periodic battery/motor events + immediate device-change events (`StatusCollector` — PEN-124) |

**StatusCollector intervals:** battery every 60 s, motor every 10 s (both configurable).
Device connect/disconnect events are collected **immediately** via `DeviceManager` callbacks.

## Code style
- Follow PEP 8; prefer descriptive names and small functions.
- Add type hints where practical; keep public APIs documented with docstrings.
- Centralize hardware interactions in `DeviceManager` and avoid duplicated port mappings.
- Default to standard library/testing tools; avoid adding new deps unless necessary.

## PR instructions
- Ensure `pytest` passes before opening/merging.
- Keep PRs scoped; document hardware assumptions/limitations in the description.
- Use imperative, concise titles (e.g., "Add gyro fallback handling").
