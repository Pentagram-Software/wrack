# CatRecognizer — GCP Infrastructure (PEN-24)

This directory contains scripts to set up the GCP project infrastructure required by the CatRecognizer ML pipeline — enabling APIs, creating GCS buckets, provisioning service accounts with least-privilege IAM roles, and verifying access with a smoke test.

## Overview

| Resource | Value |
|---|---|
| GCP project | `wrack-control` (override via `GCP_PROJECT_ID`) |
| Region | `europe-west3` |
| Training-data bucket | `<PROJECT>-cat-recognizer-training-data` |
| Model-artifacts bucket | `<PROJECT>-cat-recognizer-models` |
| Artifact Registry repo | `cat-recognizer` (Docker, `europe-west3`) |
| Data collector SA | `cat-recognizer-data@<PROJECT>.iam.gserviceaccount.com` |
| Trainer SA | `cat-recognizer-trainer@<PROJECT>.iam.gserviceaccount.com` |

## Service Account Roles (least-privilege)

| Service Account | Resource | Role |
|---|---|---|
| `cat-recognizer-data` | `training-data` bucket | `roles/storage.objectAdmin` |
| `cat-recognizer-trainer` | `training-data` bucket | `roles/storage.objectViewer` |
| `cat-recognizer-trainer` | `models` bucket | `roles/storage.objectAdmin` |
| `cat-recognizer-trainer` | Artifact Registry `cat-recognizer` | `roles/artifactregistry.writer` |

No roles are granted at the **project level** — all bindings are resource-scoped.

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`) installed and authenticated
- Authenticated account must have:
  - `roles/serviceusage.serviceUsageAdmin` (to enable APIs)
  - `roles/iam.serviceAccountAdmin` + `roles/iam.serviceAccountKeyAdmin` (to create SAs and keys)
  - `roles/storage.admin` (to create buckets and set bucket-level IAM)
  - `roles/artifactregistry.admin` (to create AR repos and set repo-level IAM)

```bash
gcloud auth login
gcloud config set project wrack-control
```

## Step-by-step Setup

### 1. Enable required APIs

```bash
GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-apis.sh
```

APIs enabled:
- `storage.googleapis.com` — Cloud Storage
- `artifactregistry.googleapis.com` — Artifact Registry
- `containerregistry.googleapis.com` — Container Registry (legacy compatibility)

### 2. Create buckets, service accounts, and IAM bindings

```bash
GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-iam.sh
```

Both scripts are **idempotent** — safe to re-run.

Optional flags for `setup-iam.sh`:

| Flag | Description |
|---|---|
| `--key-dir PATH` | Directory to write JSON keys (default: `./keys`) |
| `--store-in-secret-manager` | Upload keys to GCP Secret Manager |
| `--skip-buckets` | IAM only — skip bucket creation |
| `--dry-run` | Print all commands without executing |

### 3. Store keys securely

Keys are written to `cloud/cat-recognizer/keys/` (gitignored). **Never commit them.**

**Option A — GitHub Actions secrets:**

```bash
# Copy key contents to clipboard and create secrets in GitHub UI
cat cloud/cat-recognizer/keys/cat-recognizer-data-key.json
#  → GitHub secret name: CAT_RECOGNIZER_DATA_SA_KEY

cat cloud/cat-recognizer/keys/cat-recognizer-trainer-key.json
#  → GitHub secret name: CAT_RECOGNIZER_TRAINER_SA_KEY

# Delete local key files after storing
rm cloud/cat-recognizer/keys/*.json
```

**Option B — GCP Secret Manager:**

```bash
GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-iam.sh \
  --store-in-secret-manager
```

Secrets created: `cat-recognizer-data-key`, `cat-recognizer-trainer-key`

**Option C — Both (recommended for production)**

### 4. Smoke-test access

```bash
# Test the data collector SA (expects write access to training-data bucket)
bash cloud/cat-recognizer/smoke-test.sh --mode=data

# Test the trainer SA (expects read-only on training-data, write on models)
bash cloud/cat-recognizer/smoke-test.sh --mode=trainer
```

Or run the Python script directly with a specific credentials file:

```bash
GOOGLE_APPLICATION_CREDENTIALS=cloud/cat-recognizer/keys/cat-recognizer-data-key.json \
  python3 cloud/cat-recognizer/smoke_test.py \
  --mode=data \
  --project=wrack-control
```

## Dry-run mode

Both scripts and the shell wrapper support `--dry-run`, which prints every
`gcloud` / `python3` command without executing it:

```bash
GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-iam.sh --dry-run
bash cloud/cat-recognizer/smoke-test.sh --mode=trainer --dry-run
```

## Running the unit tests

```bash
cd /path/to/repo
python3 -m pytest cloud/cat-recognizer/tests/ -v
```

No GCP credentials are required — all GCS calls are mocked.

## Security notes

- Service account keys are excluded from git via `.gitignore` (`keys/`, `*-key.json`).
- Rotate keys via `gcloud iam service-accounts keys delete KEY_ID --iam-account=<SA_EMAIL>` and re-run `setup-iam.sh`.
- All IAM bindings are **bucket-scoped** or **repository-scoped**, not project-wide.

## Related documentation

- [`docs/cat-recognizer/setup-iam.md`](../../docs/cat-recognizer/setup-iam.md) — detailed IAM runbook
- [`edge/vision/README.md`](../../edge/vision/README.md) — ML pipeline architecture
- [`cloud/bigquery/setup-iam.sh`](../bigquery/setup-iam.sh) — pattern reference (telemetry SA)
