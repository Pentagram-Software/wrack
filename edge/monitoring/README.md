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

Entirely via environment variables, reusing the same variables the video
streamer's telemetry already uses (this collector runs on the same
physical Pi and authenticates as the same device):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `TELEMETRY_ENDPOINT` | yes | — | `unifiedIngress` Cloud Function URL |
| `RPI_DEVICE_ID` | no | `rpi-camera-01` | Device identity — reused from the video streamer, since it's the same physical device |
| `TELEMETRY_DEVICE_TOKEN` | yes | `""` | Per-device token, provisioned via `cloud/functions/setup-device-tokens.sh` |
| `SYSTEM_METRICS_INTERVAL` | no | `30` | Seconds between collection ticks — placeholder, matching `HeartbeatSender`'s own default on the EV3 side; no PRD freshness target is defined yet for Pi OS resource gauges specifically |

## Running

```bash
cd edge/monitoring
TELEMETRY_ENDPOINT=https://europe-central2-wrack-control.cloudfunctions.net/unifiedIngress \
TELEMETRY_DEVICE_TOKEN=<your-per-device-token> \
python3 system_metrics_collector.py
```

Runs in the foreground, ticking every `SYSTEM_METRICS_INTERVAL` seconds
until interrupted (`Ctrl+C`) or sent `SIGTERM`.

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

Create `~/robot/edge/monitoring/system-metrics.env` (referenced by the unit
file's `EnvironmentFile=`, and never committed to git) with the real
`TELEMETRY_ENDPOINT` / `TELEMETRY_DEVICE_TOKEN` values:

```bash
TELEMETRY_ENDPOINT=https://europe-central2-wrack-control.cloudfunctions.net/unifiedIngress
TELEMETRY_DEVICE_TOKEN=<your-per-device-token>
```

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
