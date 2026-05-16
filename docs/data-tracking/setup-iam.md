# Telemetry IAM Setup — PEN-155

This document describes how to create and configure the `telemetry-writer` service account that writes events to the `wrack_telemetry` BigQuery dataset.

**Depends on:** PEN-100 (BigQuery dataset `wrack_telemetry` must already exist — see `cloud/bigquery/deploy.sh`).

---

## Overview

| Resource | Value |
|---|---|
| Service account | `telemetry-writer@wrack-control.iam.gserviceaccount.com` |
| IAM role | `roles/bigquery.dataEditor` |
| Scope | `wrack_telemetry` dataset only (not project-wide) |
| Key storage | GitHub Actions secret `TELEMETRY_SA_KEY` + GCP Secret Manager `telemetry-writer-key` |

The role is bound at **dataset level**, not project level, to enforce least privilege: the service account can read/write rows in `wrack_telemetry` but cannot access any other GCP resource.

---

## Prerequisites

- Google Cloud SDK installed (`gcloud`, `bq`)
- Authenticated as a project admin with:
  - `roles/iam.serviceAccountAdmin` (to create service accounts)
  - `roles/iam.serviceAccountKeyAdmin` (to generate keys)
  - `roles/bigquery.admin` on the project or dataset (to set dataset IAM)
- Python 3.9+ (used by the IAM policy helper script)
- The `wrack_telemetry` dataset must already exist (run `cloud/bigquery/deploy.sh` first)

---

## Running the setup script

```bash
# From the repository root
GCP_PROJECT_ID=wrack-control bash cloud/bigquery/setup-iam.sh
```

The script is **idempotent** — running it multiple times is safe.

### Optional flags

| Flag | Description |
|---|---|
| `--key-file PATH` | Where to write the JSON key (default: `./telemetry-writer-key.json`) |
| `--store-in-secret-manager` | Also upload the key to GCP Secret Manager as `telemetry-writer-key` |
| `--dry-run` | Print every command without executing it |

Example with Secret Manager storage:

```bash
GCP_PROJECT_ID=wrack-control bash cloud/bigquery/setup-iam.sh \
  --store-in-secret-manager \
  --key-file /tmp/telemetry-writer-key.json
```

---

## What the script does

1. **Sets the active project** to `$GCP_PROJECT_ID`.
2. **Creates service account** `telemetry-writer` (skips if already exists).
3. **Grants `roles/bigquery.dataEditor`** on the `wrack_telemetry` dataset:
   - Reads the current dataset IAM policy with `bq get-iam-policy`.
   - Merges the new binding using `iam_policy_helper.py` (Python — no `jq` dependency).
   - Applies the updated policy with `bq set-iam-policy`.
4. **Generates a JSON key** to `./telemetry-writer-key.json` (chmod 600).
5. *(Optional)* **Stores the key** in GCP Secret Manager.
6. **Verifies** the service account exists and the IAM binding is in place.
7. **Prints next steps** for storing the key securely.

---

## Storing the key securely

### Option A — GitHub Actions secret (required for CI/CD)

Use this so that GitHub Actions workflows can authenticate as `telemetry-writer` to write events.

```bash
# 1. Copy the JSON key content to your clipboard
cat telemetry-writer-key.json

# 2. In GitHub: Settings → Secrets and variables → Actions → New repository secret
#      Name:  TELEMETRY_SA_KEY
#      Value: <paste the entire JSON content>

# 3. Delete the local file
rm telemetry-writer-key.json
```

### Option B — GCP Secret Manager (required for runtime services)

Any GCP service (Cloud Functions, Cloud Run) that writes telemetry can retrieve the key at runtime rather than needing it baked into a deployment.

```bash
# Either pass --store-in-secret-manager to setup-iam.sh, or run manually:
gcloud secrets create telemetry-writer-key \
  --data-file=telemetry-writer-key.json \
  --replication-policy=automatic \
  --project=wrack-control

rm telemetry-writer-key.json
```

To grant a Cloud Function permission to read the secret:

```bash
gcloud secrets add-iam-policy-binding telemetry-writer-key \
  --member="serviceAccount:<FUNCTION_SA>@wrack-control.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=wrack-control
```

### Option C — Both (recommended for production)

Run `setup-iam.sh --store-in-secret-manager` to upload to Secret Manager, then follow Option A to add `TELEMETRY_SA_KEY` to GitHub Actions secrets.

---

## Using the key in GitHub Actions

```yaml
- name: Authenticate as telemetry-writer
  uses: google-github-actions/auth@v2
  with:
    credentials_json: ${{ secrets.TELEMETRY_SA_KEY }}
```

---

## Verifying the setup manually

```bash
# Confirm the service account exists
gcloud iam service-accounts describe \
  telemetry-writer@wrack-control.iam.gserviceaccount.com \
  --project=wrack-control

# Confirm dataset-level IAM binding
bq get-iam-policy wrack-control:wrack_telemetry

# Test a write (requires the key to be active)
export GOOGLE_APPLICATION_CREDENTIALS=./telemetry-writer-key.json
bash cloud/bigquery/test-insert.sh
```

---

## Security notes

- The key file is excluded from git via `.gitignore` (`*-key.json`).
- **Never commit service account keys** to version control.
- Rotate the key annually or immediately on suspected compromise:
  ```bash
  # List key IDs
  gcloud iam service-accounts keys list \
    --iam-account=telemetry-writer@wrack-control.iam.gserviceaccount.com

  # Delete an old key
  gcloud iam service-accounts keys delete KEY_ID \
    --iam-account=telemetry-writer@wrack-control.iam.gserviceaccount.com
  ```
- The `roles/bigquery.dataEditor` role at dataset scope allows creating, updating, and deleting tables inside `wrack_telemetry` but grants no access to any other project resource.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `bq get-iam-policy` fails | Dataset doesn't exist | Run `cloud/bigquery/deploy.sh` first (PEN-100) |
| `PERMISSION_DENIED` creating SA | Insufficient gcloud permissions | Ensure your account has `roles/iam.serviceAccountAdmin` |
| IAM binding not visible in GCP console | Eventual consistency | Wait 30–60 s and refresh |
| Key file already exists warning | Previous run generated a key | Old key-id is printed; delete it via `gcloud iam service-accounts keys delete` |

---

## Related documentation

- `cloud/bigquery/deploy.sh` — Creates the `wrack_telemetry` dataset and tables (PEN-100)
- `cloud/bigquery/iam_policy_helper.py` — Python helper for dataset-level IAM JSON
- `cloud/bigquery/tests/test_iam_policy_helper.py` — Unit tests for the helper
- `docs/data-tracking/architecture.md` — End-to-end telemetry ingest flow *(PEN-157)*
