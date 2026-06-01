#!/bin/bash
# smoke-test.sh — Convenience wrapper around smoke_test.py
# PEN-24: Verify CatRecognizer service account access end-to-end
#
# Usage:
#   bash cloud/cat-recognizer/smoke-test.sh [options]
#
# Options:
#   --mode data|trainer        Which SA to test (default: data)
#   --key-dir PATH             Directory containing JSON keys (default: ./keys)
#   --project PROJECT_ID       GCP project (default: $GCP_PROJECT_ID or wrack-control)
#   --dry-run                  Print commands without executing them
#
# The script sets GOOGLE_APPLICATION_CREDENTIALS to the appropriate key file
# and then delegates to smoke_test.py.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ID="${GCP_PROJECT_ID:-wrack-control}"
MODE="data"
KEY_DIR="${SCRIPT_DIR}/keys"
DRY_RUN=false

# ── Argument parsing ────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      if [[ $# -lt 2 || "$2" == -* ]]; then
        echo "Error: --mode requires data|trainer" >&2; exit 2
      fi
      MODE="$2"; shift ;;
    --key-dir)
      if [[ $# -lt 2 || "$2" == -* ]]; then
        echo "Error: --key-dir requires a path" >&2; exit 2
      fi
      KEY_DIR="$2"; shift ;;
    --project)
      if [[ $# -lt 2 || "$2" == -* ]]; then
        echo "Error: --project requires a project ID" >&2; exit 2
      fi
      PROJECT_ID="$2"; shift ;;
    --dry-run) DRY_RUN=true ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

BUCKET_TRAINING="${PROJECT_ID}-cat-recognizer-training-data"
BUCKET_MODELS="${PROJECT_ID}-cat-recognizer-models"

case "${MODE}" in
  data)
    KEY_FILE="${KEY_DIR}/cat-recognizer-data-key.json"
    EXTRA_ARGS="--bucket=${BUCKET_TRAINING}"
    ;;
  trainer)
    KEY_FILE="${KEY_DIR}/cat-recognizer-trainer-key.json"
    EXTRA_ARGS="--bucket-data=${BUCKET_TRAINING} --bucket-models=${BUCKET_MODELS}"
    ;;
  *)
    echo "Error: --mode must be 'data' or 'trainer'" >&2
    exit 2
    ;;
esac

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "[DRY-RUN] GOOGLE_APPLICATION_CREDENTIALS=${KEY_FILE} \\"
  echo "  python3 ${SCRIPT_DIR}/smoke_test.py \\"
  echo "  --mode=${MODE} --project=${PROJECT_ID} ${EXTRA_ARGS}"
  exit 0
fi

if [[ ! -f "${KEY_FILE}" ]]; then
  echo "Error: key file not found: ${KEY_FILE}" >&2
  echo "Run setup-iam.sh first, or pass --key-dir to point to your keys directory." >&2
  exit 1
fi

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 not found" >&2
  exit 1
fi

# Ensure google-cloud-storage is installed
if ! python3 -c "import google.cloud.storage" &>/dev/null; then
  echo "Installing google-cloud-storage..."
  pip3 install --quiet google-cloud-storage
fi

export GOOGLE_APPLICATION_CREDENTIALS="${KEY_FILE}"
exec python3 "${SCRIPT_DIR}/smoke_test.py" \
  --mode="${MODE}" \
  --project="${PROJECT_ID}" \
  ${EXTRA_ARGS}
