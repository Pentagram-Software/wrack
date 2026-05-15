#!/bin/bash
# Set up IAM for Wrack telemetry service account (PEN-155)
#
# Creates a dedicated service account with minimal permissions for writing
# telemetry data to BigQuery. Permissions are scoped to the wrack_telemetry
# dataset only — no project-level IAM roles are granted.
#
# Usage:
#   GCP_PROJECT_ID=wrack-control bash cloud/bigquery/setup-iam.sh
#
# Options:
#   --key-output-file <path>  Write service account JSON key to this path.
#                             Defaults to: telemetry-writer-key.json (in CWD).
#   --skip-key-generation     Create the SA and set permissions but do not
#                             generate a key file (use when key already exists).
#   --dry-run                 Print commands that would run without executing.
#
# Prerequisites:
#   - gcloud CLI authenticated with a principal that has:
#       iam.serviceAccounts.create, iam.serviceAccounts.list,
#       iam.serviceAccountKeys.create, bigquery.datasets.getIamPolicy,
#       bigquery.datasets.setIamPolicy on the target project/dataset.
#   - bq CLI installed (part of Google Cloud SDK).
#   - The wrack_telemetry dataset must already exist (run deploy.sh first).

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ID="${GCP_PROJECT_ID:-wrack-control}"
DATASET="wrack_telemetry"
SA_NAME="telemetry-writer"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SA_DISPLAY_NAME="Wrack Telemetry Writer"
SA_DESCRIPTION="Writes telemetry events to BigQuery wrack_telemetry dataset. Minimal dataset-scoped permissions only."
KEY_OUTPUT_FILE="${KEY_OUTPUT_FILE:-telemetry-writer-key.json}"
SKIP_KEY_GENERATION="${SKIP_KEY_GENERATION:-false}"
DRY_RUN="${DRY_RUN:-false}"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --key-output-file)
      KEY_OUTPUT_FILE="$2"
      shift 2
      ;;
    --skip-key-generation)
      SKIP_KEY_GENERATION="true"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--key-output-file <path>] [--skip-key-generation] [--dry-run]"
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helper: run or print commands
# ---------------------------------------------------------------------------
run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY RUN] $*"
  else
    "$@"
  fi
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
echo "=================================================="
echo "  Wrack Telemetry - IAM Setup (PEN-155)"
echo "=================================================="
echo "Project:        ${PROJECT_ID}"
echo "Dataset:        ${DATASET}"
echo "Service account: ${SA_EMAIL}"
echo "Dry run:        ${DRY_RUN}"
echo "=================================================="
echo ""

if [[ "$DRY_RUN" != "true" ]]; then
  if ! command -v gcloud &>/dev/null; then
    echo "ERROR: 'gcloud' not found. Install Google Cloud SDK:"
    echo "  https://cloud.google.com/sdk/docs/install"
    exit 1
  fi
  if ! command -v bq &>/dev/null; then
    echo "ERROR: 'bq' not found. It ships with Google Cloud SDK."
    exit 1
  fi
fi

# Ensure the correct project is active
echo "Setting active project to ${PROJECT_ID}..."
run gcloud config set project "${PROJECT_ID}"

# ---------------------------------------------------------------------------
# Step 1: Verify the dataset exists
# ---------------------------------------------------------------------------
echo ""
echo "Step 1: Verifying dataset '${DATASET}' exists..."
if [[ "$DRY_RUN" != "true" ]]; then
  if ! bq show --dataset "${PROJECT_ID}:${DATASET}" &>/dev/null; then
    echo "ERROR: Dataset '${PROJECT_ID}:${DATASET}' does not exist."
    echo "       Run cloud/bigquery/deploy.sh first to create it."
    exit 1
  fi
  echo "✓ Dataset exists"
else
  echo "[DRY RUN] Would verify dataset ${PROJECT_ID}:${DATASET}"
fi

# ---------------------------------------------------------------------------
# Step 2: Create the service account (idempotent)
# ---------------------------------------------------------------------------
echo ""
echo "Step 2: Creating service account '${SA_EMAIL}'..."
if [[ "$DRY_RUN" != "true" ]]; then
  if gcloud iam service-accounts describe "${SA_EMAIL}" \
       --project="${PROJECT_ID}" &>/dev/null 2>&1; then
    echo "✓ Service account already exists, skipping creation"
  else
    run gcloud iam service-accounts create "${SA_NAME}" \
      --project="${PROJECT_ID}" \
      --display-name="${SA_DISPLAY_NAME}" \
      --description="${SA_DESCRIPTION}"
    echo "✓ Service account created"
  fi
else
  echo "[DRY RUN] gcloud iam service-accounts create ${SA_NAME} \\"
  echo "            --project=${PROJECT_ID} \\"
  echo "            --display-name='${SA_DISPLAY_NAME}' \\"
  echo "            --description='${SA_DESCRIPTION}'"
fi

# ---------------------------------------------------------------------------
# Step 3: Grant BigQuery Data Editor on the dataset only
#
# We use `bq add-iam-policy-binding` (dataset-level IAM) rather than
# `gcloud projects add-iam-policy-binding` (project-level IAM) to keep
# the blast radius as small as possible.
# ---------------------------------------------------------------------------
echo ""
echo "Step 3: Granting roles/bigquery.dataEditor on dataset '${DATASET}' only..."
run bq add-iam-policy-binding \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.dataEditor" \
  "${PROJECT_ID}:${DATASET}"
echo "✓ Dataset-level IAM binding set"

# ---------------------------------------------------------------------------
# Step 4: Generate service account key (unless skipped)
# ---------------------------------------------------------------------------
if [[ "$SKIP_KEY_GENERATION" == "true" ]]; then
  echo ""
  echo "Step 4: Skipping key generation (--skip-key-generation flag set)"
else
  echo ""
  echo "Step 4: Generating service account key..."

  if [[ "$DRY_RUN" != "true" ]]; then
    # Safety: refuse to overwrite an existing key file silently
    if [[ -f "$KEY_OUTPUT_FILE" ]]; then
      echo "ERROR: Key file '${KEY_OUTPUT_FILE}' already exists."
      echo "       Delete it first or use --key-output-file to specify a different path."
      exit 1
    fi

    run gcloud iam service-accounts keys create "${KEY_OUTPUT_FILE}" \
      --iam-account="${SA_EMAIL}" \
      --project="${PROJECT_ID}"

    chmod 600 "${KEY_OUTPUT_FILE}"
    echo "✓ Key written to: ${KEY_OUTPUT_FILE} (mode 600)"
  else
    echo "[DRY RUN] gcloud iam service-accounts keys create ${KEY_OUTPUT_FILE} \\"
    echo "            --iam-account=${SA_EMAIL} \\"
    echo "            --project=${PROJECT_ID}"
  fi
fi

# ---------------------------------------------------------------------------
# Step 5: Verify IAM binding
# ---------------------------------------------------------------------------
echo ""
echo "Step 5: Verifying IAM bindings on dataset..."
if [[ "$DRY_RUN" != "true" ]]; then
  bq get-iam-policy "${PROJECT_ID}:${DATASET}" \
    | grep -A2 "telemetry-writer" || true
  echo "✓ Verification complete"
else
  echo "[DRY RUN] bq get-iam-policy ${PROJECT_ID}:${DATASET}"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=================================================="
echo "  IAM setup completed successfully!"
echo "=================================================="
echo ""
echo "Service account:  ${SA_EMAIL}"
echo "Role granted:     roles/bigquery.dataEditor"
echo "Scope:            ${PROJECT_ID}:${DATASET} (dataset only)"
if [[ "$SKIP_KEY_GENERATION" != "true" && "$DRY_RUN" != "true" ]]; then
  echo "Key file:         ${KEY_OUTPUT_FILE}"
  echo ""
  echo "IMPORTANT — Secure key storage:"
  echo "  1. Add the key contents as a GitHub Actions secret named TELEMETRY_SA_KEY:"
  echo "       gh secret set TELEMETRY_SA_KEY < ${KEY_OUTPUT_FILE}"
  echo "     or via: https://github.com/YOUR_ORG/wrack/settings/secrets/actions"
  echo ""
  echo "  2. Delete the local key file after storing it:"
  echo "       rm -f ${KEY_OUTPUT_FILE}"
  echo ""
  echo "  3. Do NOT commit the key file to git."
  echo "     (It is listed in .gitignore as *-key.json)"
fi
echo ""
echo "Next steps:"
echo "  - Add BigQuery client to Cloud Functions (PEN-156 / PEN-110)"
echo "  - Reference service account key via TELEMETRY_SA_KEY secret in CI/CD"
echo ""
