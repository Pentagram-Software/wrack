# CatRecognizer IAM Setup — PEN-24

This runbook describes how to provision the GCP infrastructure for the CatRecognizer
ML pipeline: enabling required APIs, creating GCS storage buckets, and setting up
service accounts with least-privilege IAM roles.

---

## Architecture overview

```
Edge (Raspberry Pi)                  GCP (wrack-control)
──────────────────                   ───────────────────────────────────
cat-recognizer-data SA
  ──objectAdmin──►  gs://<proj>-cat-recognizer-training-data
                              │
                              │ (read-only)
                              ▼
cat-recognizer-trainer SA ────────►  Training job (local workstation / CI)
  ──objectAdmin──►  gs://<proj>-cat-recognizer-models
  ──writer──────►   Artifact Registry  europe-west3/cat-recognizer (Docker)
```

---

## Resources created

### GCS Buckets

| Bucket | Purpose | Region |
|---|---|---|
| `<PROJECT>-cat-recognizer-training-data` | Raw frames and annotation files uploaded from edge | `europe-west3` |
| `<PROJECT>-cat-recognizer-models` | Exported ONNX model artifacts from training runs | `europe-west3` |

Both buckets use **uniform bucket-level access** and **public access prevention**.

### Service Accounts

| Service Account | Purpose |
|---|---|
| `cat-recognizer-data@<PROJECT>.iam.gserviceaccount.com` | Edge device uploads training frames to GCS |
| `cat-recognizer-trainer@<PROJECT>.iam.gserviceaccount.com` | Training script reads data, writes model artifacts, pushes containers |

### IAM Bindings (all resource-scoped — no project-level grants)

| SA | Resource | Role | Justification |
|---|---|---|---|
| `cat-recognizer-data` | training-data bucket | `roles/storage.objectAdmin` | Must upload, list, and optionally delete frames |
| `cat-recognizer-trainer` | training-data bucket | `roles/storage.objectViewer` | Read-only access to training frames |
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

### Step 2 — Create buckets, service accounts, and IAM bindings

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
| `--skip-buckets` | Recreate SA/IAM only; skip bucket creation |
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
# Data collector SA: expects write access to training-data bucket
bash cloud/cat-recognizer/smoke-test.sh --mode=data

# Trainer SA: expects read-only on training-data, write on models bucket
bash cloud/cat-recognizer/smoke-test.sh --mode=trainer
```

Or run the Python script directly:

```bash
GOOGLE_APPLICATION_CREDENTIALS=cloud/cat-recognizer/keys/cat-recognizer-data-key.json \
  python3 cloud/cat-recognizer/smoke_test.py \
  --mode=data \
  --project=wrack-control
```

Expected output when all checks pass:

```
==================================================
  CatRecognizer GCS Smoke Test (PEN-24)
==================================================
  Credentials: cloud/cat-recognizer/keys/cat-recognizer-data-key.json

Mode: data  (bucket: gs://wrack-control-cat-recognizer-training-data)
  ✓ list objects in gs://wrack-control-cat-recognizer-training-data (found 0 object(s))
  ✓ write object gs://wrack-control-cat-recognizer-training-data/_smoke-test/...
  ✓ read object gs://wrack-control-cat-recognizer-training-data/_smoke-test/...

==================================================
  Results: 3 passed, 0 failed
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
| API not enabled error | APIs not enabled | Run `setup-apis.sh` first |

---

## Related documentation

- [`cloud/cat-recognizer/README.md`](../../cloud/cat-recognizer/README.md) — script reference
- [`edge/vision/README.md`](../../edge/vision/README.md) — ML pipeline architecture (training workflow)
- [`cloud/bigquery/setup-iam.sh`](../../cloud/bigquery/setup-iam.sh) — pattern reference (telemetry SA)
- [`docs/data-tracking/setup-iam.md`](../data-tracking/setup-iam.md) — BigQuery telemetry IAM setup
