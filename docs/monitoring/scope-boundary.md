# System Monitoring vs. Wrack Analytics — Scope Boundary

## Why this document exists

The [System Monitoring PRD](https://linear.app/pentagram-software/project/system-monitoring-467664671f7e) requires, as a delivery qualifier, that *"analytics remains explicitly separated from monitoring scope and storage expectations."*

Two projects in this repo both touch "telemetry," and it is easy to route a new data point to the wrong one:

- **System Monitoring** (`edge/monitoring/`, `docs/monitoring/`, Grafana Cloud) — real-time operational health.
- **Wrack Analytics** ("System Telemetry" project — `cloud/bigquery/`, `shared/telemetry-types/`, `robot/controller/telemetry/`) — historical event storage in BigQuery.

This document is the single source of truth for which system owns a given metric or event. A reviewer unfamiliar with the project should be able to use it to make that call in under 2 minutes.

## What belongs in System Monitoring

Real-time, short-horizon, operational data whose only job is to answer "is the system healthy *right now*, and if not, why?"

- **Liveness / heartbeat** signals (EV3 alive, streamer process alive)
- **Resource utilization** (Pi CPU, memory, temperature)
- **Error rates** (Cloud Function error %, ingestion failures)
- **Operational dashboards** — one unified, above-the-fold view of current system posture
- **Slack alerts** — pager/warning notifications with direct links to the dashboard and recent logs
- **Recent logs** — last 5 minutes, for immediate triage, not archival
- **72-hour retention** — high-granularity data is deliberately short-lived; nothing here is a system of record

If the question is "what is happening in the last few minutes, and does someone need to act now," it belongs here.

## What belongs in Wrack Analytics

Historical, structured event data whose job is retrospective analysis, trends, and future ML use, not incident response.

- **Historical event storage** in BigQuery (`wrack_telemetry.events`), partitioned/clustered for querying over days-to-months
- **Long-term trends** — usage patterns, command frequency, battery degradation over weeks
- **Dashboards for analysis** — Looker Studio, ad-hoc SQL, not live triage
- **ML-ready datasets** — future feature engineering, anomaly detection training data
- **No fixed short retention** — analytics is explicitly the system that owns retention *beyond* what monitoring keeps

If the question is "how has this behaved over time, or what can we learn in aggregate," it belongs here.

## Decision table

Given a new data point, ask these questions in order:

| # | Question | If yes → | If no → |
|---|----------|----------|---------|
| 1 | Does answering "is the system healthy right now" require this data within seconds? | System Monitoring | Go to 2 |
| 2 | Is this needed to page/alert someone during an active incident? | System Monitoring | Go to 3 |
| 3 | Is the primary value in analyzing trends, aggregates, or training data over days/weeks/months? | Wrack Analytics | Go to 4 |
| 4 | Would losing this data after 72 hours break an operational workflow? | System Monitoring | Wrack Analytics |

Both questions can be "yes" for the same underlying signal — see the dual-homed example below. In that case, the signal is emitted to **both** systems, each serving its own purpose. It is not one-or-the-other, it is "which system needs this for its stated purpose."

## Examples from each domain

| Data point | Owner | Why |
|---|---|---|
| `wrack_ev3_alive` (Prometheus gauge) | System Monitoring | Liveness signal, drives the 10s-detection Slack alert; no historical value once superseded |
| `node_hwmon_temp_celsius` (Pi temperature) | System Monitoring | Real-time threshold alert (pager > 75°C); triage only |
| `namedprocess_namegroup_num_procs` (streamer liveness) | System Monitoring | Process-dead detection, feeds the "streamer dead" alert |
| `ev3_command_sent` / `command_executed` event | Wrack Analytics | Historical record of robot usage, not needed for live health; stored in `wrack_telemetry.events` |
| `api_request` event (Cloud Function) | Wrack Analytics | Used for usage analysis and cost tracking; the *rate* of errors (not each row) is what monitoring cares about |
| `battery_status` event | Wrack Analytics | Long-term battery degradation trend; not an incident signal by itself |
| `video_stream_health` (FPS, drop rate, client count) | **Both** — primary System Monitoring, secondary Wrack Analytics | Real-time FPS/drop-rate drives live dashboards and alerts (System Monitoring); the same event is also emitted to BigQuery for historical stream-quality analysis (see [PEN-167](https://linear.app/pentagram-software/issue/PEN-167/telemetry-pen-132-video-stream-health-telemetry)) |
| Cloud Function error-rate *aggregate* (last 10s) | System Monitoring | Drives the pager alert |
| Cloud Function error *events* (individual rows, historical) | Wrack Analytics | Forensic/trend analysis of what failed and when |

## Rule of thumb

If removing the data after 72 hours would break something an on-call responder needs *today*, it's monitoring. If the value only appears when you look back over days or weeks, it's analytics. When in doubt, check whether the consuming system is Grafana (monitoring) or BigQuery/Looker Studio (analytics) — that's usually the fastest tell.
