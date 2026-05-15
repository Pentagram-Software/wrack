# BigQuery Telemetry Infrastructure

Scripts and schemas for the Wrack telemetry data warehouse in Google BigQuery.

## Overview

| File | Purpose |
|------|---------|
| `deploy.sh` | Creates the `wrack_telemetry` dataset, `events` table, and SQL views |
| `setup-iam.sh` | Creates the `telemetry-writer` service account with minimal dataset-scoped permissions |
| `schemas/events.sql` | `events` table DDL — partitioned by date, clustered by `source` and `event_type` |
| `schemas/views.sql` | Pre-built SQL views (`events_last_24h`, `battery_events`, etc.) |
| `test-insert.sh` | Inserts a sample row and queries views — useful for smoke-testing |

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud` + `bq` CLIs)
- A GCP principal authenticated via `gcloud auth login` (or a service account with sufficient IAM) with:
  - `bigquery.datasets.create` (for `deploy.sh`)
  - `iam.serviceAccounts.create`, `iam.serviceAccountKeys.create`, `bigquery.datasets.setIamPolicy` (for `setup-iam.sh`)
- Target project set or provided via `GCP_PROJECT_ID` environment variable (default: `wrack-control`)

---

## Step 1 — Deploy BigQuery Infrastructure

Run this first. It creates the dataset, events table, and views:

```bash
# Default project (wrack-control)
bash cloud/bigquery/deploy.sh

# Specify a different project
GCP_PROJECT_ID=my-project bash cloud/bigquery/deploy.sh
```

The script is idempotent — safe to re-run after schema changes.

---

## Step 2 — Create the Telemetry Service Account (PEN-155)

Run `setup-iam.sh` **after** `deploy.sh`. It:

1. Creates service account `telemetry-writer@<project>.iam.gserviceaccount.com`
2. Grants `roles/bigquery.dataEditor` on the `wrack_telemetry` **dataset only** (no project-level IAM)
3. Generates a JSON key file

```bash
# Default project, key written to ./telemetry-writer-key.json
bash cloud/bigquery/setup-iam.sh

# Specify project and key output path
GCP_PROJECT_ID=my-project bash cloud/bigquery/setup-iam.sh \
  --key-output-file /tmp/telemetry-sa-key.json

# Dry run — print commands without executing
bash cloud/bigquery/setup-iam.sh --dry-run
```

### Options

| Flag | Description |
|------|-------------|
| `--key-output-file <path>` | Path for the generated JSON key (default: `telemetry-writer-key.json`) |
| `--skip-key-generation` | Create SA and set permissions but do not generate a key |
| `--dry-run` | Print commands that would run without executing them |

---

## Step 3 — Store the Key Securely

The JSON key produced by `setup-iam.sh` must be stored as a **GitHub Actions secret** and then deleted locally. **Never commit a key file to git.**

### Add to GitHub Actions secrets

```bash
# Using the GitHub CLI
gh secret set TELEMETRY_SA_KEY < telemetry-writer-key.json

# Or via the GitHub web UI:
# https://github.com/YOUR_ORG/wrack/settings/secrets/actions
```

### Delete the local key

```bash
rm -f telemetry-writer-key.json
```

The pattern `*-key.json` is in `.gitignore` as an additional safety net.

### Secret naming convention

| Secret | Contents | Used by |
|--------|----------|---------|
| `GCP_SA_KEY` | Admin service account key (deploy BigQuery infra) | `.github/workflows/deploy-bigquery.yml` |
| `TELEMETRY_SA_KEY` | `telemetry-writer` key (insert events only) | Future telemetry Cloud Function |

---

## Service Account Details

| Attribute | Value |
|-----------|-------|
| Email | `telemetry-writer@wrack-control.iam.gserviceaccount.com` |
| Display name | Wrack Telemetry Writer |
| IAM role | `roles/bigquery.dataEditor` |
| IAM scope | `wrack_telemetry` dataset only |
| Purpose | Streaming / batch insert of telemetry events from Cloud Functions and EV3 |

The `BigQuery Data Editor` role at dataset level allows the service account to:
- Insert rows into tables (`bigquery.tables.updateData`)
- Read table data (`bigquery.tables.getData`)
- List tables (`bigquery.tables.list`)

It does **not** grant the ability to create/drop datasets, run jobs project-wide, or access any other dataset.

---

## Verifying the IAM Binding

After running `setup-iam.sh`, confirm the binding with:

```bash
bq get-iam-policy wrack-control:wrack_telemetry
```

Expected output includes:

```json
{
  "bindings": [
    {
      "members": ["serviceAccount:telemetry-writer@wrack-control.iam.gserviceaccount.com"],
      "role": "roles/bigquery.dataEditor"
    }
  ]
}
```

---

## CI/CD Integration

The `deploy-bigquery` workflow (`.github/workflows/deploy-bigquery.yml`) runs `deploy.sh` automatically on pushes to `main` that touch `cloud/bigquery/**`. It uses the `GCP_SA_KEY` secret for authentication.

IAM setup (`setup-iam.sh`) is a **one-time manual operation** — it is intentionally not part of the automated CI pipeline to avoid unintended key rotation. Re-run it manually only when:
- Setting up a fresh GCP project
- Rotating the service account key

---

## Smoke Test

After both scripts run successfully, validate end-to-end insertion:

```bash
bash cloud/bigquery/test-insert.sh
```
