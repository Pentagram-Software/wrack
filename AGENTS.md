# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Wrack is a monorepo for controlling a LEGO Mindstorms EV3 robot. The dev-testable services are:
- **Web Controller** (`clients/web/`) — Next.js 15 + React 19 app at `http://localhost:3000`
- **Cloud Functions** (`cloud/functions/`) — GCP Cloud Functions bridge (runs locally via `functions-framework` at `http://localhost:8080`)
- **WebSocket Video Bridge** (`edge/ws-bridge/`) — Node.js bridge that forwards UDP video frames to browser clients at `ws://localhost:8765`

Other components (robot firmware, Raspberry Pi edge, iOS app) require physical hardware and cannot be tested in the cloud VM.

### Running services

- **Web app**: `cd clients/web && npm run dev` (port 3000). Env vars in `.env.local` (copy from `.env.local.example`).
- **Cloud functions**: `cd cloud/functions && npm start` (port 8080). Env vars in `.env` (copy from `.env.example`). Default API key: `your-secret-api-key` via `X-API-Key` header.
- **WebSocket bridge**: `cd edge/ws-bridge && npm start` (ws port 8765, health at http://localhost:8765/health). Set `PI_HOST` env var to the Pi's IP; defaults to `127.0.0.1`.

### Linting

- Web: `cd clients/web && npm run lint` — pre-existing lint errors exist (5 warnings in `ConnectionTest.tsx`, `EV3StatusPanel.tsx`, `MapVisualization.tsx`, `TurretControls.tsx`, `robot-api.ts`; `CameraView.tsx` was rewritten and is clean).
- Cloud functions: `cd cloud/functions && npm run lint` — no eslint config present; this command fails.
- `npm run build` in `clients/web` fails due to the same pre-existing lint errors. The dev server works fine.

### Testing

- **Robot controller** (Python): `cd robot/controller && source .venv/bin/activate && python -m pytest event_handler/tests/ robot_controllers/tests/ wake_word/tests/ error_reporting/tests/ telemetry/tests/ -q`. The top-level `tests/` dir and `ev3_devices/tests/` have import issues (legacy module paths and missing pybricks mocks) that are pre-existing.
- **Cloud functions** (Jest): `cd cloud/functions && npm test` — runs Jest unit tests covering authentication, command validation, dispatching, error handling, and telemetry event schema validation (`schemas.test.ts`).
- **Web client** (Vitest): `cd clients/web && npm test` — runs unit tests for videoStream library, CameraView component, ThemeToggle, and themeStore.
- **WebSocket bridge** (Jest): `cd edge/ws-bridge && npm test` — runs unit tests for frame extraction (H.264/JPEG/pickle detection) and UDP protocol reassembly.
- Refer to `robot/controller/AGENTS.md` for Python-specific dev guidance.

### System dependencies

- `python3.12-venv` and `python3.12-dev` plus `portaudio19-dev` are required for the robot controller Python venv (the `precise-runner` dep needs `pyaudio` which needs these C headers).
- Node.js 22 works fine for both `clients/web` and `cloud/functions` despite `cloud/functions/package.json` declaring `engines.node: "20"`.
