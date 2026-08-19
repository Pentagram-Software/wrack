#!/bin/bash
# setup-infra.sh — Provision Phase 2 GCS storage + IAM for CatRecognizer (PEN-255–257)
#
# Implements tasks 5.1-5.3 of openspec/changes/add-cat-detection-identification/tasks.md:
# three GCS buckets (raw-data w/ 90-day lifecycle, processed-data, models) and two
# least-privilege service accounts (data-collector, trainer/export).
#
# Deliberately built clean, not resurrected from the unmerged cursor/pen-24 / cursor/pen-25
# branches — see design.md's "GCP infrastructure is rebuilt clean" decision. This session did
# NOT run this script against real GCP (the /opsx:apply session that generated it chose the
# "code-only, hand off GCP provisioning" path) — review it, then run for real when ready.
#
# Usage:
#   GCP_PROJECT_ID=wrack-control bash setup-infra.sh [--dry-run]
#
# Prerequisites:
#   gcloud (authenticated, with roles/storage.admin and roles/iam.serviceAccountAdmin)

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-wrack-control}"

BUCKET_RAW="${PROJECT_ID}-cat-recognizer-raw-data"
BUCKET_PROCESSED="${PROJECT_ID}-cat-recognizer-processed-data"
BUCKET_MODELS="${PROJECT_ID}-cat-recognizer-models"
RAW_LIFECYCLE_DAYS=90

SA_DATA_NAME="cat-recognizer-data-collector"
SA_TRAINER_NAME="cat-recognizer-trainer-export"
SA_DATA_EMAIL="${SA_DATA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SA_TRAINER_EMAIL="${SA_TRAINER_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

DRY_RUN=false

# ── Argument parsing ────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

# ── Helpers ─────────────────────────────────────────────────────────────────────
run() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] $*"
  else
    "$@"
  fi
}

info()  { echo "  ▸ $*"; }
ok()    { echo "  ✓ $*"; }

# `describe` returns non-zero (404) when the resource doesn't exist yet —
# that's the expected/common case on a first run, not an error, so callers
# must not let `set -e` treat it as one.
bucket_exists() {
  gcloud storage buckets describe "gs://$1" --project="${PROJECT_ID}" >/dev/null 2>&1
}

service_account_exists() {
  gcloud iam service-accounts describe "$1" --project="${PROJECT_ID}" >/dev/null 2>&1
}

print_banner() {
  echo ""
  echo "=================================================="
  echo "  CatRecognizer — Phase 2 Infra Setup (PEN-255–257)"
  echo "=================================================="
  echo "  Project:          ${PROJECT_ID}"
  echo "  Buckets:          ${BUCKET_RAW}"
  echo "                    ${BUCKET_PROCESSED}"
  echo "                    ${BUCKET_MODELS}"
  echo "  Service accounts: ${SA_DATA_EMAIL}"
  echo "                    ${SA_TRAINER_EMAIL}"
  [[ "${DRY_RUN}" == "true" ]] && echo "  Mode:             DRY-RUN (no changes)"
  echo "=================================================="
  echo ""
}

check_prerequisites() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    info "Dry-run: skipping prerequisite validation"
    return
  fi
  command -v gcloud >/dev/null 2>&1 || { echo "gcloud not found" >&2; exit 1; }
  ok "gcloud found"
}

# ── 5.1: three GCS buckets, raw-data with 90-day lifecycle ─────────────────────
create_buckets() {
  info "Creating buckets..."
  for bucket in "${BUCKET_RAW}" "${BUCKET_PROCESSED}" "${BUCKET_MODELS}"; do
    if [[ "${DRY_RUN}" != "true" ]] && bucket_exists "${bucket}"; then
      info "gs://${bucket} already exists — skipping create"
      continue
    fi
    run gcloud storage buckets create "gs://${bucket}" \
      --project="${PROJECT_ID}" \
      --uniform-bucket-level-access \
      --location=EU
  done
  ok "buckets created (or already existed)"

  info "Applying ${RAW_LIFECYCLE_DAYS}-day lifecycle rule to ${BUCKET_RAW}..."
  local lifecycle_file
  lifecycle_file="$(mktemp)"
  cat > "${lifecycle_file}" <<EOF
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": ${RAW_LIFECYCLE_DAYS}}
    }
  ]
}
EOF
  run gcloud storage buckets update "gs://${BUCKET_RAW}" --lifecycle-file="${lifecycle_file}"
  rm -f "${lifecycle_file}"
  ok "lifecycle rule applied"
}

# ── 5.2: folder structure via zero-byte .keep placeholders ─────────────────────
create_folder_structure() {
  info "Creating folder structure..."
  local tmp_keep
  tmp_keep="$(mktemp)"
  for cat in ryfka chaja lea; do
    run gcloud storage cp "${tmp_keep}" "gs://${BUCKET_RAW}/${cat}/.keep"
  done
  for split in train val test; do
    run gcloud storage cp "${tmp_keep}" "gs://${BUCKET_PROCESSED}/${split}/.keep"
  done
  rm -f "${tmp_keep}"
  ok "folder structure created"
}

# ── 5.3: two least-privilege service accounts, bucket-scoped IAM only ──────────
create_service_accounts() {
  info "Creating service accounts..."
  if [[ "${DRY_RUN}" != "true" ]] && service_account_exists "${SA_DATA_EMAIL}"; then
    info "${SA_DATA_EMAIL} already exists — skipping create"
  else
    run gcloud iam service-accounts create "${SA_DATA_NAME}" \
      --project="${PROJECT_ID}" \
      --display-name="CatRecognizer Data Collector" \
      --description="Writes raw per-cat photos to ${BUCKET_RAW}; read-only on ${BUCKET_PROCESSED}"
  fi

  if [[ "${DRY_RUN}" != "true" ]] && service_account_exists "${SA_TRAINER_EMAIL}"; then
    info "${SA_TRAINER_EMAIL} already exists — skipping create"
  else
    run gcloud iam service-accounts create "${SA_TRAINER_NAME}" \
      --project="${PROJECT_ID}" \
      --display-name="CatRecognizer Trainer/Export" \
      --description="Reads raw photos, writes processed splits and exported ONNX models. No Artifact Registry roles — no containerized training to authorize."
  fi
  ok "service accounts created (or already existed)"

  info "Granting bucket-scoped IAM roles (no project-level roles)..."
  run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_RAW}" \
    --member="serviceAccount:${SA_DATA_EMAIL}" --role="roles/storage.objectAdmin"
  run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_PROCESSED}" \
    --member="serviceAccount:${SA_DATA_EMAIL}" --role="roles/storage.objectViewer"

  run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_RAW}" \
    --member="serviceAccount:${SA_TRAINER_EMAIL}" --role="roles/storage.objectViewer"
  run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_PROCESSED}" \
    --member="serviceAccount:${SA_TRAINER_EMAIL}" --role="roles/storage.objectAdmin"
  run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_MODELS}" \
    --member="serviceAccount:${SA_TRAINER_EMAIL}" --role="roles/storage.objectAdmin"
  ok "IAM bindings applied"
}

print_next_steps() {
  echo ""
  echo "Next steps:"
  echo "  1. Verify access with smoke_test.py (task 5.4):"
  echo "       python3 smoke_test.py --project ${PROJECT_ID}"
  echo "  2. Run enrollment (task 6.3/6.4) writing raw photos to gs://${BUCKET_RAW}/{ryfka,chaja,lea}/"
  echo "  3. See README.md for the full IAM matrix and bucket layout"
  echo ""
}

main() {
  print_banner
  check_prerequisites
  create_buckets
  create_folder_structure
  create_service_accounts
  print_next_steps
}

# Guard so tests/test_setup_infra.sh can `source` this file (to call
# bucket_exists/create_buckets/etc. directly against a mocked `gcloud`)
# without running the full flow as a side effect of sourcing.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main
fi
