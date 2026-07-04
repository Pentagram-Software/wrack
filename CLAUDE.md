# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Monorepo Structure

| Path | Language | Purpose |
|------|----------|---------|
| `robot/controller/` | Python (pybricks-micropython) | EV3 firmware — PS4 + network remote |
| `edge/video-streamer/` | Python | Raspberry Pi camera → UDP video stream |
| `edge/monitoring/` | Alloy/River | Grafana Alloy config for RPi edge metrics (textfile scraping) |
| `cloud/functions/` | Node.js | GCP Cloud Functions HTTP → EV3 TCP bridge |
| `clients/ios/` | Swift | iPhone robot control + H.264 video |
| `clients/web/` | TypeScript | Next.js web controller |
| `shared/video-protocol/` | Swift / TypeScript | UDP frame format spec + platform libs |
| `shared/telemetry-types/` | TypeScript / Python / JSON | Telemetry event schemas, types, and validation utilities |
| `samples/python-video-receiver/` | Python | macOS test receiver for video stream |
| `cloud/bigquery/` | Bash / SQL / Python | BigQuery DDL, IAM setup, telemetry helpers |
| `docs/data-tracking/` | Markdown | Telemetry architecture and IAM setup guides |

Sub-components `clients/web/` and `cloud/functions/` have their own `CLAUDE.md` files with additional detail.

## Common Commands

```bash
# Web dev server (http://localhost:3000)
make web
# or
cd clients/web && npm run dev

# Run all tests
make test

# Web tests only (Vitest)
cd clients/web && npm test

# Web – single test file
cd clients/web && npx vitest run src/path/to/file.test.ts

# Web linting
cd clients/web && npm run lint

# Cloud functions tests (Jest — includes TypeScript schema tests)
cd cloud/functions && npm test

# Robot controller tests (Python — includes telemetry schema tests)
cd robot/controller && source .venv/bin/activate && python -m pytest event_handler/tests/ robot_controllers/tests/ wake_word/tests/ error_reporting/tests/ telemetry/tests/ -q

# Deploy GCP functions
make deploy-cloud   # runs gcloud functions deploy

# Deploy edge code to Raspberry Pi
make deploy-edge    # rsync to pi@raspberrypi.local

# BigQuery telemetry — deploy dataset + tables (PEN-100)
GCP_PROJECT_ID=wrack-control bash cloud/bigquery/deploy.sh

# BigQuery telemetry — create/configure telemetry-writer service account (PEN-155)
GCP_PROJECT_ID=wrack-control bash cloud/bigquery/setup-iam.sh
# See docs/data-tracking/setup-iam.md for full instructions and key-storage guidance

# BigQuery IAM helper — unit tests
python -m pytest cloud/bigquery/tests/ -v
```

## System Architecture

### Control Path
```
iOS / Web ──HTTP POST (X-API-Key)──► GCP Cloud Functions ──TCP JSON──► EV3 (port 27700)
```
- Cloud function (`cloud/functions/index.js`) validates commands, enforces speed 0–2000 and max duration 10 s, then forwards JSON over TCP.
- EV3 listens via `RemoteController` (`robot/controller/robot_controllers/remote_controller.py`).

### Video Path
```
Raspberry Pi camera ──H.264 UDP chunks (port 9999)──► iOS App / Web / Python clients
```
- Streamer (`edge/video-streamer/`) sends `FRAME_START` + `CHUNK` packets; protocol spec in `shared/video-protocol/UDP_Frame_Format_Documentation.md`.
- Clients reassemble chunks by `frame_id` before decoding H.264.

### Telemetry Path
```
EV3 sensors ──► Raspberry Pi vision model ──► BigQuery (wrack_telemetry dataset)
```
- Dataset DDL in `cloud/bigquery/schemas/`; deploy with `cloud/bigquery/deploy.sh`.
- IAM setup (service account `telemetry-writer`) via `cloud/bigquery/setup-iam.sh`; see `docs/data-tracking/setup-iam.md`.

## Web Client (`clients/web/`)

- **Framework**: Next.js 15 App Router, React 19, TypeScript 5
- **State**: Zustand stores in `src/stores/` (e.g. `themeStore.ts` persists theme to localStorage under key `wrack-theme`)
- **Styling**: Tailwind CSS 4 + MUI v7 (both in use). Layout classes use MD3 semantic tokens (e.g. `bg-background`, `text-on-surface-variant`) defined in `src/design-system/`.
- **Design system**: `src/design-system/tokens/` contains generated MD3 color/spacing/typography tokens; `src/design-system/themes/` wraps them into a MUI theme. Generate updated tokens with `npm run tokens:transform`.
- **API client**: `src/lib/robot-api.ts` exports a singleton `robotController`; all robot commands go through it.
- **Testing**: Vitest with two projects — `unit` (jsdom + @testing-library/react, files matching `src/**/*.test.{ts,tsx}`) and `storybook` (Playwright/Chromium headless).
- **Storybook**: `npm run storybook` (port 6006); stories live in `src/stories/`.
- **Environment**: copy `.env.local.example` → `.env.local`; `NEXT_PUBLIC_GCP_FUNCTION_URL`, `NEXT_PUBLIC_API_KEY`, `NEXT_PUBLIC_GCP_PROJECT_ID`, `NEXT_PUBLIC_GCP_REGION` required.

## EV3 Robot Controller (`robot/controller/`)

- Runs pybricks-micropython on the EV3 brick. Entry point: `main.py`.
- `DeviceManager` wraps all hardware with graceful degradation — always check `device_manager.is_device_available()` before using a device.
- Motor ports: Drive L = Port A, Drive R = Port D, Turret = Port C; sensors: Ultrasonic = S2, Gyro = S3.
- Run tests (desktop Python): `cd robot/controller && python -m pytest tests/`

### MicroPython compatibility (mandatory check — always run for this repo)

Every change that touches `robot/controller/` or its dependencies (anything imported into that
tree, e.g. Python bits of `shared/telemetry-types/`) must be checked for Pybricks/MicroPython
compatibility, not just validated against the desktop pytest suite. **The pytest suite runs on
CPython and will not catch any MicroPython-only incompatibility below** — passing tests are
necessary but not sufficient for a change in this tree. Production has repeatedly hit bugs where
code was syntactically/semantically valid CPython but broke on-device; check for these classes
explicitly on every change:

- **Partial stdlib modules**: `import x` succeeding does not mean the whole module works. Some
  MicroPython builds ship partial modules that import fine but raise `AttributeError` (not
  `ImportError`) the moment a specific attribute is used (hit with `datetime`, `re`). Guard with
  `try/except` and catch the specific exception types actually possible — not a bare
  `except Exception`, which can silently mask real bugs (see the `schemas` import guard in
  `telemetry/collector.py` for the pattern).
- **Partial module attributes**: a successful `import uuid` does not guarantee `uuid.uuid4` exists.
  Check `hasattr()` for the specific function/attribute you depend on before relying on it.
- **No builtin `format()`**: some builds omit the builtin `format(value, spec)` function entirely
  (hit generating a zero-padded hex string). This does **not** apply to the `str.format()` method
  (e.g. `"{}-{}".format(a, b)`), which is fine on MicroPython and is the established pattern used
  throughout `telemetry/` — prefer it, or `%`-style formatting, over the bare `format()` builtin.
- **No `from __future__ import annotations`**: unavailable on MicroPython. Function-signature
  annotations are evaluated eagerly — use the `_TypingStub` fallback pattern already established
  in `telemetry/*.py` for `typing` imports.
- **No PEP 526 annotations on non-simple targets**: `self.x: Type = value` or `d[k]: Type = value`
  raise `SyntaxError` at compile time — this is worse than a runtime bug because it takes down the
  whole module before any `try/except` guard can run. Annotations are only supported on simple
  names. Use a plain assignment.
- **`threading.Thread()`**: only accepts `target`/`args` — passing `daemon` or `name` raises
  `TypeError`. `Thread.join()` may not accept `timeout` — wrap in `try/except TypeError` with a
  fallback (see `status_collector.py`).
- **Minimal HTTP libraries** (`urequests`): don't assume parity with `requests` — e.g. `post()` may
  not accept `timeout`. Try the full call first, catch `TypeError`, and retry with a reduced kwarg
  set (see `telemetry/sender.py::_http_post`).
- **`open()`**: no `encoding` kwarg — catch `TypeError` and retry without it (see
  `telemetry/collector.py::_open_text`).

When fixing one of these, add a regression test even though it runs on CPython and can't reproduce
the MicroPython-specific failure directly — simulate the failure mode (e.g. inject a fake module
into `sys.modules` missing the attribute, or patch the relevant `_HAS_*` flag) so the fallback path
itself stays covered.

## Cloud Functions (`cloud/functions/`)

- `index.js` — HTTP handler and command validation; emits `api_request` telemetry event on every request
- `api-telemetry.js` — Fire-and-forget `api_request` telemetry logging to BigQuery (used by `index.js`); wraps BigQuery inserts in `setImmediate` so they never block the HTTP response
- `auth.js` — `X-API-Key` header authentication
- `robot-server.py` — Python TCP server running on the EV3 (separate deploy)
- Deploy: `cd cloud/functions && npm run deploy` or `gcloud builds submit --config cloudbuild.yaml`

## Workflow Conventions

- All agent-generated code changes must go to a **PR**, not a direct commit to `main`.
- Break large tasks into **small, separately committed pieces**.
- Write and run unit tests for new functionality; run the full test suite before opening a PR.
