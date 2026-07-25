# Raspberry Pi System Metrics Collector (PEN-192)

Collects CPU usage %, memory usage %, and CPU temperature from the
Raspberry Pi's own `/proc` and `/sys` filesystems and posts them to the
unified Cloud Function ingress (`unifiedIngress`, PEN-227) as a
`system_metrics` event tagged `type="health"`, so the health leg
(`healthLegPush`, PEN-228) routes them onward to Grafana Cloud.

This replaces the Grafana Alloy-based plan for Pi OS metrics — see
[docs/monitoring/architecture.md](../../docs/monitoring/architecture.md)
for the full pipeline and why Alloy was dropped. `alloy/config.alloy` in
this directory is a prepared-but-never-deployed config kept for reference
only; it is superseded by `system_metrics_collector.py`, not complementary
to it.

## What it collects

| Metric | Source | Notes |
|---|---|---|
| `cpu_percent` | `/proc/stat` | Computed from the delta between two samples' idle/total jiffie counters — the previous tick's sample is kept in memory, so the very first tick after startup produces no usable value and is skipped (bootstrap) |
| `memory_percent` | `/proc/meminfo` | `100 * (1 - MemAvailable / MemTotal)` — matches `node_memory_MemAvailable_bytes` / `node_memory_MemTotal_bytes` semantics (accounts for reclaimable cache/buffers, not just free RAM) |
| `cpu_temp_c` | `/sys/class/thermal/thermal_zone0/temp` | Millidegrees C / 1000. Optional — omitted for a tick (not a dropped tick) if this path is missing/unreadable on a given Pi model |

All three are numeric fields on one `system_metrics` payload, so
`cloud/functions/otlp-mapper.js`'s `wrack.<event_type>.<field>` auto-naming
produces `wrack.system_metrics.cpu_percent`,
`wrack.system_metrics.memory_percent`, and `wrack.system_metrics.cpu_temp_c`
as OTLP gauge metrics (translated by Grafana Cloud into
`wrack_system_metrics_cpu_percent` etc. — see
[docs/monitoring/ev3-health-dashboard.md](../../docs/monitoring/ev3-health-dashboard.md)
for how that Prometheus/Mimir name derivation works and why it still needs
manual confirmation in Metrics Explorer before it's trusted in a dashboard
query).

## Configuration

Credentials live in `system-metrics.env` next to this README — the same
file the video streamer reads. **`make deploy-edge` writes it on the Pi**
from `PI_DEVICE_TOKEN` + `GCP_PROJECT_ID` (see
[`../scripts/README.md`](../scripts/README.md)); do not commit it.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `TELEMETRY_ENDPOINT` | yes | — | `unifiedIngress` URL (derived at deploy time) |
| `RPI_DEVICE_ID` | no | `rpi-camera-01` | Device identity — shared with the video streamer |
| `TELEMETRY_DEVICE_TOKEN` | yes | — | Per-device token (`PI_DEVICE_TOKEN` secret) |
| `SYSTEM_METRICS_INTERVAL` | no | `30` | Seconds between collection ticks |

`main()` auto-loads `system-metrics.env` via `edge/pi_telemetry_env.py`
when `TELEMETRY_ENDPOINT` is unset.

## Running

After deploy (env file already on the Pi):

```bash
cd ~/robot/edge/monitoring
python3 system_metrics_collector.py
```

Or start collector **and** video streamer together:
[`../scripts/start-all.sh`](../scripts/README.md) / `make start-edge`.

## Installing as a systemd service (manual step)

`systemd/wrack-system-metrics.service` is a prepared unit file — like
`alloy/config.alloy` before it, it is **not** installed automatically by
`make deploy-edge` (which only rsyncs files onto the Pi). The unit's
`WorkingDirectory` / `ExecStart` / `EnvironmentFile` paths match
`make deploy-edge`'s default `PI_REMOTE_PATH` (`/home/pi/robot/edge/`).
If you override `PI_REMOTE_PATH` at deploy time, edit those three paths
in the unit before enabling it.

To actually run this as a persistent, auto-restarting service:

```bash
# On the Pi, after `make deploy-edge` has synced edge/ to ~/robot/edge:
sudo cp ~/robot/edge/monitoring/systemd/wrack-system-metrics.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wrack-system-metrics.service
```

The unit's `EnvironmentFile=` points at `system-metrics.env`, which
`make deploy-edge` already writes on the Pi (rsync excludes it so laptop
copies cannot overwrite secrets). No manual env-file creation is needed
after a successful deploy.

Check status/logs with `systemctl status wrack-system-metrics` /
`journalctl -u wrack-system-metrics -f`.

## Testing

```bash
cd edge/monitoring
python -m pytest tests/ -q
```

Follows the same conventions as
[`edge/vision/telemetry/tests/`](../vision/telemetry/tests/) and
[`edge/video-streamer/tests/`](../video-streamer/tests/): file reads and
network sends are mocked, so these tests run on any machine (no real Pi
hardware, no live network) and in CI (`.github/workflows/ci-edge.yml`).
