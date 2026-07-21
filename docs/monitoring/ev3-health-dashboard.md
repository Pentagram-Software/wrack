# EV3 Health Dashboard (PEN-231)

A standalone Grafana Cloud dashboard for EV3 robot health. v1 ships a single
panel — EV3 battery percentage — and is expected to grow as more EV3 health
metrics come online (e.g. [PEN-200](https://linear.app/pentagram-software/issue/PEN-200/ev3-live-battery-and-motor-health-metrics-in-grafana)'s
voltage gauge + motor/turret availability indicators).

This replaces the EV3 portion of the unified dashboard originally planned in
PEN-198 (canceled — split into per-component dashboards so each ships
independently; see [docs/monitoring/architecture.md](architecture.md)).

## Where the data comes from

[PEN-234](https://linear.app/pentagram-software/issue/PEN-234/restore-ev3-health-only-telemetry-without-controller-lag)
merges battery state onto the EV3's existing liveness heartbeat: one
`device_status` event tagged `type="health"`, posted through the unified
ingress → health leg → Grafana Cloud OTLP gateway pipeline described in
[docs/monitoring/architecture.md](architecture.md). The payload's `percentage`
field (0–100, estimated remaining charge) is what this dashboard's panel
plots.

Per `cloud/functions/otlp-mapper.js`'s `wrack.<event_type>.<field>` metric
auto-naming, the pre-translation OTLP metric name is
**`wrack.device_status.percentage`**.

### Deriving the expected Prometheus/Mimir metric name

The expected final name, **`wrack_device_status_percentage`**, isn't a blind
guess — it's derived from two code-verifiable facts plus Grafana's own
published translation spec:

1. **`cloud/functions/health-leg.js`** creates the metric via
   `meterProvider.getMeter(...).createGauge(point.name)` — no `unit` is ever
   set on the OTel gauge descriptor.
2. **Grafana Cloud's documented OTLP-to-Prometheus translation**
   ([OTLP: format considerations](https://grafana.com/docs/grafana-cloud/send-data/otlp/otlp-format-considerations/),
   backed by [`grafana/mimir-otlptranslator`](https://github.com/grafana/mimir-otlptranslator))
   converts `.`/`-` to `_` (`wrack.device_status.percentage` →
   `wrack_device_status_percentage`), and only appends a suffix — e.g. the
   `_ratio` suffix for a gauge — when the metric's OTel **unit is `1`**.
   Since no unit is set at all here (not "1", just absent), no suffix
   should apply under Mimir's default `UnderscoreEscapingWithSuffixes`
   translation strategy.

That's strong, citable evidence, but it stops short of a live confirmation:
this repo can't verify that the specific Grafana Cloud stack in use is
actually running that documented default translation strategy rather than a
non-default override, since that's a live account/stack setting invisible
from outside. **This is why `provision-dashboard.sh provision` requires an
explicit `--metric-name` flag** (see [Usage](#usage) below) rather than the
dashboard JSON shipping this derived value as its committed, active query —
per PEN-231 code review, an unverified name (however well-derived) must
never be the thing an automated provisioning run actually ships. The
dashboard JSON's panel instead queries the placeholder
`__CONFIRM_METRIC_NAME__`, substituted at provisioning time.

## Files

| File | Purpose |
|---|---|
| `cloud/monitoring/dashboards/wrack-ev3-health.json` | The dashboard definition (Grafana dashboard JSON model). Fixed `uid: wrack-ev3-health` so re-provisioning updates the same dashboard rather than creating duplicates. |
| `cloud/monitoring/provision-dashboard.sh` | Provisioning script — `store-credentials` (one-time credential setup) and `provision` (POST the dashboard to Grafana Cloud) subcommands. |
| `cloud/monitoring/write_dashboard_credentials.py` | Builds the `{grafana_url, token}` JSON payload for `store-credentials`, called out of the shell script the same way `write_credentials.py` is for the OTLP push credentials. |
| `cloud/monitoring/build_dashboard_request.py` | Wraps the dashboard JSON in the `/api/dashboards/db` request envelope (`{dashboard, overwrite: true, message}`) and substitutes the `__CONFIRM_METRIC_NAME__` placeholder with the `--metric-name` value, called out of the shell script for `provision`. |
| `cloud/monitoring/tests/test_dashboard_json.py`, `test_write_dashboard_credentials.py`, `test_build_dashboard_request.py`, `test_provision_dashboard.sh` | Unit/regression tests — see [Testing](#testing) below. |

## Usage

### 1. Store the dashboards:write credential (one-time, per environment)

Grafana Cloud has no self-service API to bootstrap this token — same
limitation `setup-grafana-secret.sh` documents for the existing OTLP push
credential. It must be created by hand in Grafana Cloud's UI (Security →
Access Policies), scoped to `dashboards:write` **only**, and must **not**
reuse or broaden the existing `grafana-cloud-push-credentials` secret (that
one is scoped to `metrics:write` + `logs:write` for the health-leg push
function and stays that way — see
[docs/monitoring/architecture.md](architecture.md)).

```bash
GRAFANA_DASHBOARD_TOKEN=<access-policy-token> \
  bash cloud/monitoring/provision-dashboard.sh store-credentials \
    --grafana-url https://<your-stack-slug>.grafana.net
```

This stores `{"grafana_url": ..., "token": ...}` in the GCP Secret Manager
secret `grafana-cloud-dashboard-credentials` (project `wrack-control` by
default; override with `GCP_PROJECT_ID` / `--secret-name`). Add `--dry-run`
to preview without touching gcloud or Secret Manager.

### 2. Provision the dashboard

```bash
GCP_PROJECT_ID=wrack-control bash cloud/monitoring/provision-dashboard.sh provision \
  --metric-name wrack_device_status_percentage
```

Reads the credential back from Secret Manager, substitutes `--metric-name`
into the dashboard JSON's placeholder query, and POSTs the result to
`<grafana_url>/api/dashboards/db`. Safe to re-run — `overwrite: true` plus
the dashboard's fixed `uid` make this idempotent.

`--metric-name` is **required** for a real (non-`--dry-run`) call — the
committed dashboard JSON queries the placeholder `__CONFIRM_METRIC_NAME__`,
never a live value, so this can't silently provision an unverified guess
(PEN-231 code review). See [Deriving the expected Prometheus/Mimir metric
name](#deriving-the-expected-prometheusmimir-metric-name) above for where
`wrack_device_status_percentage` comes from and what's still worth
confirming in Metrics Explorer before trusting it. Add `--dry-run` to
validate the dashboard JSON and preview the plan without any network/gcloud
calls — `--metric-name` is optional there.

## Manual steps required before this is live

This dashboard was authored and tested in a sandbox with no live Grafana
Cloud credentials and no live EV3 — the following can only be done by a
human with real access, in this order:

1. **Create the `dashboards:write` Access Policy token** in Grafana Cloud's
   UI and run `store-credentials` (above) to store it.
2. **Confirm the real metric name before provisioning for real.** Once
   [PEN-234](https://linear.app/pentagram-software/issue/PEN-234/restore-ev3-health-only-telemetry-without-controller-lag)
   is live and the EV3 is posting heartbeats with battery data, open Grafana
   Cloud's Metrics Explorer and search for a metric derived from
   `wrack.device_status.percentage`. [Deriving the expected Prometheus/Mimir
   metric name](#deriving-the-expected-prometheusmimir-metric-name) above
   explains why `wrack_device_status_percentage` is the well-reasoned
   expectation — confirm it (or find the actual name, if it differs).
3. **Run `provision-dashboard.sh provision --metric-name <confirmed-name>`**
   for real (not `--dry-run`) to actually create the dashboard in Grafana
   Cloud with that confirmed name substituted in.
4. **Visually confirm** the panel renders without errors and shows live data
   with the EV3 online.

## Testing

```bash
cd cloud/monitoring
python -m pytest tests/test_dashboard_json.py tests/test_write_dashboard_credentials.py tests/test_build_dashboard_request.py -v
bash tests/test_provision_dashboard.sh
```

All four are wired into `.github/workflows/ci-cloud-monitoring.yml`. None of
them touch a real Grafana Cloud stack or GCP project — the bash regression
test fakes `gcloud`/`curl` on `PATH`, the same approach
`test_setup_grafana_secret.sh` uses. Live rendering/data verification is
covered by the manual steps above, not by automated tests.
