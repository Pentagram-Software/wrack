# CI/CD Rollback Guide

This document covers how to roll back failed deployments for Cloud Functions and BigQuery infrastructure.

## Cloud Functions Rollback

### Finding the last good deployment

Every successful deployment is tagged automatically:

```bash
# List recent deployment tags
git tag --list 'deploy/cloud-functions/*' --sort=-creatordate | head -10
```

### Rollback to a previous version

```bash
# 1. Identify the tag you want to roll back to (e.g. deploy/cloud-functions/20260503-142301-abc12345)
TAG=deploy/cloud-functions/20260503-142301-abc12345

# 2. Check out that commit
git checkout $TAG

# 3. Re-deploy manually using gcloud
gcloud functions deploy controlRobot \
  --gen2 \
  --runtime nodejs20 \
  --trigger-http \
  --allow-unauthenticated \
  --region europe-central2 \
  --source ./cloud/functions \
  --entry-point controlRobot \
  --project <GCP_PROJECT_ID> \
  --set-env-vars ROBOT_HOST=<ROBOT_HOST>,ROBOT_PORT=<ROBOT_PORT>,API_KEY=<API_KEY>

# 4. Return to main
git checkout main
```

### Using Cloud Functions revision history (GCP Console)

Cloud Functions Gen2 keeps a history of deployed revisions via Cloud Run:

1. Open [GCP Console → Cloud Run](https://console.cloud.google.com/run)
2. Select the `controlRobot` service
3. Go to **Revisions** tab
4. Click on a previous revision → **Manage Traffic** → send 100% traffic to it

This is the fastest rollback path — no re-deploy required.

---

## BigQuery Rollback

BigQuery DDL (CREATE TABLE IF NOT EXISTS, CREATE OR REPLACE VIEW) is **idempotent** — re-running the scripts is safe and will not destroy data.

### Schema changes (columns added)

BigQuery does not support removing columns. If a bad column was added:

1. The data is safe — the column exists but may be empty.
2. You cannot roll back the schema itself; the fix is a follow-up migration.
3. Document the issue and raise a new ticket.

### View definition rollback

Views can be freely redefined. To roll back a view to a previous definition:

```bash
# 1. Find the last good tag
git tag --list 'deploy/bigquery/*' --sort=-creatordate | head -10

# 2. Check out the old schemas
TAG=deploy/bigquery/20260503-142301-abc12345
git show $TAG:cloud/bigquery/schemas/views.sql > /tmp/views-old.sql

# 3. Apply the old view definitions
bq query --use_legacy_sql=false < /tmp/views-old.sql
```

### Dataset/table accidentally deleted (recovery)

BigQuery has a 7-day table snapshot window. To recover a deleted table:

```bash
# Replace SNAPSHOT_TIME with Unix timestamp in milliseconds (up to 7 days ago)
bq cp \
  "wrack_telemetry.events@<SNAPSHOT_TIME_MS>" \
  "wrack_telemetry.events_recovered"
```

Then rename/swap as needed via the BQ Console.

---

## Deployment Status Reference

| Where | What to check |
|---|---|
| GitHub Actions | [Actions tab](https://github.com/Pentagram-Software/wrack/actions) — all workflow runs |
| Cloud Functions | [GCP Console → Functions](https://console.cloud.google.com/functions) → `controlRobot` |
| Cloud Run revisions | [GCP Console → Cloud Run](https://console.cloud.google.com/run) → `controlRobot` → Revisions |
| BigQuery | [GCP Console → BigQuery](https://console.cloud.google.com/bigquery) → `wrack_telemetry` dataset |
| Deployment tags | `git tag --list 'deploy/*' --sort=-creatordate` |

---

## Required GitHub Secrets

The following secrets must be configured in the repository for CD to work:

| Secret | Description |
|---|---|
| `GCP_SA_KEY` | GCP Service Account JSON key with deployment permissions |
| `GCP_PROJECT_ID` | GCP project ID (e.g. `wrack-control`) |
| `ROBOT_HOST` | Robot's IP/hostname |
| `ROBOT_PORT` | Robot's port |
| `GCP_API_KEY` | API key for the Cloud Function |
| `SLACK_WEBHOOK_URL` | Incoming webhook URL for deploy notifications |

Configure at: **GitHub → Settings → Secrets and variables → Actions**
