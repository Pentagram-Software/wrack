# Edge session scripts

Session-only helpers to start/stop the Raspberry Pi edge processes with one
command. These are **not** systemd units — processes die on reboot or when
you run `stop-all.sh`. For reboot-persistent metrics, see the prepared
systemd unit in [`../monitoring/README.md`](../monitoring/README.md).

## Processes

| Process | Entry point | Notes |
|---|---|---|
| Video streamer | `video-streamer/streamer.py` | Defaults to UDP (`STREAMER_CHOICE=1`) because the streamer's `__main__` still prompts interactively for protocol |
| System metrics collector | `monitoring/system_metrics_collector.py` | Loads `monitoring/system-metrics.env` if present (same file the systemd unit uses) |

PID files and logs live under `edge/run/` (gitignored):

- `run/video-streamer.pid`, `run/system-metrics.pid`
- `run/logs/video-streamer.log`, `run/logs/system-metrics.log`

## On the Pi

After `make deploy-edge` has synced `edge/` to `~/robot/edge` (the default
`PI_REMOTE_PATH`):

```bash
bash ~/robot/edge/scripts/start-all.sh
bash ~/robot/edge/scripts/stop-all.sh
```

Create `~/robot/edge/monitoring/system-metrics.env` before starting if you
want the metrics collector to actually reach `unifiedIngress`:

```bash
TELEMETRY_ENDPOINT=https://europe-central2-wrack-control.cloudfunctions.net/unifiedIngress
TELEMETRY_DEVICE_TOKEN=<your-per-device-token>
```

## From a laptop

Same SSH/rsync defaults as `make deploy-edge` (`PI_IP`, `PI_USER`,
`PI_SSH_PORT`, `PI_REMOTE_PATH`):

```bash
make start-edge
make stop-edge
```

## Optional env

| Variable | Default | Purpose |
|---|---|---|
| `STREAMER_CHOICE` | `1` (UDP) | Answer fed to the streamer's interactive protocol prompt (`2`=TCP, `3`=HTTP) |
| `PYTHON` | `python3` | Interpreter used to launch both processes |
| `EDGE_ROOT` | parent of `scripts/` | Override for tests |

## Testing

```bash
bash edge/scripts/tests/test_start_stop.sh
```

Runs against a fake edge tree with stub Python entry points — no Pi hardware
or live network required.
