# CatRecognizer IAM Setup — PEN-25

This runbook describes how to provision the GCP infrastructure for the CatRecognizer
ML pipeline: enabling required APIs, creating GCS storage buckets with lifecycle rules
and folder structure, and setting up service accounts with least-privilege IAM roles.

---

## Architecture overview

```
Edge (Raspberry Pi)                    GCP (wrack-control)
──────────────────                     ─────────────────────────────────────────
cat-recognizer-data SA
  ──objectAdmin──►   gs://<proj>-cat-recognizer-raw-data
                               │  (ryfka/ chaja/ lea/)
                               │
                               │ (read-only)
                               ▼
cat-recognizer-trainer SA ──────────►  Training job (local workstation / CI)
  ──objectViewer──► gs://<proj>-cat-recognizer-raw-data
  ──objectAdmin───► gs://<proj>-cat-recognizer-processed-data
                               │  (train/ val/ test/)
  ──objectAdmin───► gs://<proj>-cat-recognizer-models
  ──AR writer─────► Artifact Registry  europe-west3/cat-recognizer (Docker)
```

---

## Resources created

### GCS Buckets

| Bucket | Purpose | Region | Lifecycle |
|---|---|---|---|
| `<PROJECT>-cat-recognizer-raw-data` | Raw frames uploaded from edge devices | `europe-west3` | Auto-delete after **90 days** |
| `<PROJECT>-cat-recognizer-processed-data` | Train/val/test splits and annotation files | `europe-west3` | None |
| `<PROJECT>-cat-recognizer-models` | Exported ONNX model artifacts from training runs | `europe-west3` | None |

All buckets use **uniform bucket-level access** and **public access prevention**.

#### Lifecycle rule — raw-data bucket

A lifecycle configuration file (`cloud/cat-recognizer/lifecycle-raw-data.json`) is
committed alongside `setup-iam.sh` and applied to the raw-data bucket during setup:

```json
{
  "lifecycle": {
    "rule": [
      {
        "action": { "type": "Delete" },
        "condition": { "age": 90 }
      }
    ]
  }
}
```

This causes all objects in the raw-data bucket to be automatically deleted 90 days
after creation, keeping storage costs in check as new frames are continuously uploaded.

#### Folder structure

Zero-byte `.keep` placeholder objects are created to establish the expected prefix
hierarchy in each bucket:

```
gs://<PROJECT>-cat-recognizer-raw-data/
  ryfka/.keep
  chaja/.keep
  lea/.keep

gs://<PROJECT>-cat-recognizer-processed-data/
  train/.keep
  val/.keep
  test/.keep

gs://<PROJECT>-cat-recognizer-models/
  (top-level only — no subfolders required)
```

Placeholder creation is idempotent — re-running `setup-iam.sh` skips any `.keep`
objects that already exist.

### Service Accounts

| Service Account | Purpose |
|---|---|
| `cat-recognizer-data@<PROJECT>.iam.gserviceaccount.com` | Edge device uploads raw frames to GCS raw-data bucket |
| `cat-recognizer-trainer@<PROJECT>.iam.gserviceaccount.com` | Training script reads raw data, writes processed data and model artifacts, pushes containers |

### IAM Bindings (all resource-scoped — no project-level grants)

| SA | Resource | Role | Justification |
|---|---|---|---|
| `cat-recognizer-data` | raw-data bucket | `roles/storage.objectAdmin` | Must upload, list, and optionally delete frames |
| `cat-recognizer-data` | processed-data bucket | `roles/storage.objectViewer` | Read-only access to annotations |
| `cat-recognizer-trainer` | raw-data bucket | `roles/storage.objectViewer` | Read-only access to training frames |
| `cat-recognizer-trainer` | processed-data bucket | `roles/storage.objectAdmin` | Write and manage train/val/test splits |
| `cat-recognizer-trainer` | models bucket | `roles/storage.objectAdmin` | Write and manage exported model artifacts |
| `cat-recognizer-trainer` | AR repo `cat-recognizer` | `roles/artifactregistry.writer` | Push training container images |

### Artifact Registry

| Field | Value |
|---|---|
| Repository name | `cat-recognizer` |
| Format | Docker |
| Location | `europe-west3` |

---

## Prerequisites

- Google Cloud SDK installed (`gcloud`): https://cloud.google.com/sdk/docs/install
- Authenticated as a project admin with:
  - `roles/serviceusage.serviceUsageAdmin` (enable APIs)
  - `roles/iam.serviceAccountAdmin` + `roles/iam.serviceAccountKeyAdmin`
  - `roles/storage.admin`
  - `roles/artifactregistry.admin`
- Python 3.9+ (for smoke test; no extra deps for setup scripts)

```bash
gcloud auth login
gcloud config set project wrack-control
```

---

## Running the setup

### Step 1 — Enable APIs

```bash
# From repo root:
GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-apis.sh
```

To preview without making changes:

```bash
GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-apis.sh --dry-run
```

Expected output:

```
  ✓ storage.googleapis.com — confirmed enabled
  ✓ artifactregistry.googleapis.com — confirmed enabled
  ✓ containerregistry.googleapis.com — confirmed enabled
```

### Step 2 — Create buckets, service accounts, lifecycle rules, folder structure, and IAM bindings

```bash
GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-iam.sh
```

Both scripts are idempotent — re-running is safe.

To preview without making changes:

```bash
GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-iam.sh --dry-run
```

Optional flags:

| Flag | Description |
|---|---|
| `--key-dir PATH` | Where to write JSON keys (default: `cloud/cat-recognizer/keys/`) |
| `--store-in-secret-manager` | Upload keys to Secret Manager after creation |
| `--skip-buckets` | Recreate SA/IAM only; skip bucket creation, lifecycle, and folder structure |
| `--dry-run` | Print commands, no execution |

---

## Storing keys securely

Keys are generated to `cloud/cat-recognizer/keys/` which is in `.gitignore`.
**Never commit service account key files.**

### Option A — GitHub Actions secrets

Required if CI/CD training jobs need to authenticate:

```bash
# 1. Print and copy the key JSON
cat cloud/cat-recognizer/keys/cat-recognizer-data-key.json
#  GitHub: Settings → Secrets → Actions → New repository secret
#  Name:  CAT_RECOGNIZER_DATA_SA_KEY
#  Value: <paste JSON>

cat cloud/cat-recognizer/keys/cat-recognizer-trainer-key.json
#  GitHub: Settings → Secrets → Actions → New repository secret
#  Name:  CAT_RECOGNIZER_TRAINER_SA_KEY
#  Value: <paste JSON>

# 2. Delete local key files
rm cloud/cat-recognizer/keys/*.json
```

Use in a GitHub Actions workflow:

```yaml
- name: Authenticate as cat-recognizer-trainer
  uses: google-github-actions/auth@v2
  with:
    credentials_json: ${{ secrets.CAT_RECOGNIZER_TRAINER_SA_KEY }}
```

### Option B — GCP Secret Manager

```bash
GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-iam.sh \
  --store-in-secret-manager
```

Secrets created:
- `cat-recognizer-data-key`
- `cat-recognizer-trainer-key`

To grant a Cloud Run or Cloud Function access to a secret:

```bash
gcloud secrets add-iam-policy-binding cat-recognizer-trainer-key \
  --member="serviceAccount:<FUNCTION_SA>@wrack-control.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=wrack-control
```

### Option C — Both (recommended)

Run `setup-iam.sh --store-in-secret-manager`, then add GitHub Actions secrets.

---

## Smoke test

After keys are in place, verify end-to-end access:

```bash
# Data collector SA: write to raw-data (ryfka/), read-only on processed-data
bash cloud/cat-recognizer/smoke-test.sh --mode=data

# Trainer SA: read-only on raw-data, write to processed-data (train/) and models
bash cloud/cat-recognizer/smoke-test.sh --mode=trainer
```

Or run the Python script directly:

```bash
GOOGLE_APPLICATION_CREDENTIALS=cloud/cat-recognizer/keys/cat-recognizer-data-key.json \
  python3 cloud/cat-recognizer/smoke_test.py \
  --mode=data \
  --project=wrack-control
```

Expected output when all checks pass (data mode):

```
==================================================
  CatRecognizer GCS Smoke Test (PEN-25)
==================================================
  Credentials: cloud/cat-recognizer/keys/cat-recognizer-data-key.json

Mode: data
  raw-data bucket:       gs://wrack-control-cat-recognizer-raw-data
  processed-data bucket: gs://wrack-control-cat-recognizer-processed-data
  ✓ list objects in gs://wrack-control-cat-recognizer-raw-data (found 1 object(s))
  ✓ write object gs://wrack-control-cat-recognizer-raw-data/ryfka/_smoke-test/...
  ✓ read object gs://wrack-control-cat-recognizer-raw-data/ryfka/_smoke-test/...
  ✓ write DENIED on gs://wrack-control-cat-recognizer-processed-data (expected Forbidden)
  ✓ verify .keep at gs://wrack-control-cat-recognizer-raw-data/ryfka/.keep
  ✓ verify .keep at gs://wrack-control-cat-recognizer-raw-data/chaja/.keep
  ✓ verify .keep at gs://wrack-control-cat-recognizer-raw-data/lea/.keep
  ✓ verify .keep at gs://wrack-control-cat-recognizer-processed-data/train/.keep
  ✓ verify .keep at gs://wrack-control-cat-recognizer-processed-data/val/.keep
  ✓ verify .keep at gs://wrack-control-cat-recognizer-processed-data/test/.keep

==================================================
  Results: 10 passed, 0 failed
==================================================
  ✓ All checks passed — service account access verified!
```

---

## Key rotation

```bash
# List existing keys
gcloud iam service-accounts keys list \
  --iam-account=cat-recognizer-data@wrack-control.iam.gserviceaccount.com

# Delete an old key by ID
gcloud iam service-accounts keys delete KEY_ID \
  --iam-account=cat-recognizer-data@wrack-control.iam.gserviceaccount.com

# Re-run setup-iam.sh to generate a new key (rotation is handled automatically)
GCP_PROJECT_ID=wrack-control bash cloud/cat-recognizer/setup-iam.sh
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `PERMISSION_DENIED` creating SA | Insufficient gcloud permissions | Ensure `roles/iam.serviceAccountAdmin` |
| `PERMISSION_DENIED` creating bucket | Missing `roles/storage.admin` | Grant storage admin |
| Smoke test: `bucket not found` | `setup-iam.sh` not run yet | Run `setup-iam.sh` first |
| Smoke test: `PERMISSION_DENIED` on write | Wrong key used, or wrong mode | Check `GOOGLE_APPLICATION_CREDENTIALS` path and `--mode` flag |
| Smoke test: `.keep not found` | `setup-iam.sh` not run, or `--skip-buckets` was used | Re-run without `--skip-buckets` |
| API not enabled error | APIs not enabled | Run `setup-apis.sh` first |

---

## Related documentation

- [`cloud/cat-recognizer/README.md`](../../cloud/cat-recognizer/README.md) — script reference
- [`edge/vision/README.md`](../../edge/vision/README.md) — ML pipeline architecture (training workflow)
- [`cloud/bigquery/setup-iam.sh`](../../cloud/bigquery/setup-iam.sh) — pattern reference (telemetry SA)
- [`docs/data-tracking/setup-iam.md`](../data-tracking/setup-iam.md) — BigQuery telemetry IAM setup
