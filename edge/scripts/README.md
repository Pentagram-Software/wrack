# Edge session scripts

Session-only helpers to start/stop the Raspberry Pi edge processes with one
command. These are **not** systemd units — processes die on reboot or when
you run `stop-all.sh`. For reboot-persistent metrics, see the prepared
systemd unit in [`../monitoring/README.md`](../monitoring/README.md).

## Processes

| Process | Entry point | Notes |
|---|---|---|
| Video streamer | `video-streamer/streamer.py` | Defaults to UDP (`STREAMER_CHOICE=1`). Loads shared telemetry env and enables `VideoTelemetry` for UDP when credentials are present |
| System metrics collector | `monitoring/system_metrics_collector.py` | Requires `TELEMETRY_ENDPOINT` (from the shared env file) |

PID files and logs live under `edge/run/` (gitignored):

- `run/video-streamer.pid`, `run/system-metrics.pid`
- `run/logs/video-streamer.log`, `run/logs/system-metrics.log`

## Shared telemetry env file

Both programs read `monitoring/system-metrics.env` (KEY=VALUE only — same
semantics as systemd `EnvironmentFile=`). **`make deploy-edge` writes this
file on the Pi automatically** from secrets — do not create it by hand on
the laptop (rsync excludes it so local copies cannot overwrite Pi secrets).

| Variable | Source |
|---|---|
| `TELEMETRY_ENDPOINT` | Derived as `https://europe-central2-<GCP_PROJECT_ID>.cloudfunctions.net/unifiedIngress` |
| `TELEMETRY_DEVICE_TOKEN` | GitHub secret / env `PI_DEVICE_TOKEN` |
| `RPI_DEVICE_ID` | Optional secret / env `PI_RPI_DEVICE_ID` (default `rpi-camera-01`) |

Required for deploy (Actions or local):

```bash
# GitHub Actions secrets: PI_DEVICE_TOKEN, GCP_PROJECT_ID
# (optional: PI_RPI_DEVICE_ID)
# plus existing PI_IP / PI_SSH_PRIVATE_KEY

# Local:
PI_IP=… PI_DEVICE_TOKEN=… GCP_PROJECT_ID=wrack-control make deploy-edge
```

Generate the device token with:

```bash
bash cloud/functions/setup-device-tokens.sh --device-id rpi-camera-01
```

## On the Pi

After a successful `make deploy-edge`:

```bash
bash ~/robot/edge/scripts/start-all.sh
bash ~/robot/edge/scripts/stop-all.sh
```

`start-all.sh` loads `system-metrics.env` and **fails** if
`TELEMETRY_ENDPOINT` is still unset (so the metrics collector cannot die
with a Python traceback mid-start).

## From a laptop

Same SSH/rsync defaults as `make deploy-edge` (`PI_IP`, `PI_USER`,
`PI_SSH_PORT`, `PI_REMOTE_PATH`):

```bash
make start-edge
make stop-edge

# Forward protocol choice / interpreter into the remote shell:
STREAMER_CHOICE=2 make start-edge
```

## Optional env

| Variable | Default | Purpose |
|---|---|---|
| `STREAMER_CHOICE` | `1` (UDP) | Answer fed to the streamer's interactive protocol prompt (`2`=TCP, `3`=HTTP). Forwarded by `make start-edge`. |
| `PYTHON` | `python3` | Interpreter used to launch both processes. Forwarded by `make start-edge`. |
| `EDGE_ROOT` | parent of `scripts/` | Override for tests |

## Testing

```bash
bash edge/scripts/tests/test_start_stop.sh
bash edge/scripts/tests/test_write_pi_telemetry_env.sh
cd edge && python -m pytest tests/ -q
```

Runs against a fake edge tree / stdout-only write script — no Pi hardware
or live network required.
