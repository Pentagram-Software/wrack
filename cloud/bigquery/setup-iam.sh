#!/bin/bash
# setup-iam.sh — Create and configure the telemetry-writer service account
# PEN-155: Create service account for telemetry writes
#
# Usage:
#   GCP_PROJECT_ID=wrack-control bash setup-iam.sh [options]
#
# Options:
#   --store-in-secret-manager   Also store the generated key in GCP Secret Manager
#   --key-file PATH             Output path for the JSON key (default: ./telemetry-writer-key.json)
#   --dry-run                   Print commands without executing them
#
# Prerequisites:
#   gcloud (authenticated, with roles/iam.serviceAccountAdmin and roles/resourcemanager.projectIamAdmin)
#   bq (BigQuery CLI — part of Google Cloud SDK)
#   python3

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-wrack-control}"
DATASET="wrack_telemetry"
SA_NAME="telemetry-writer"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SA_DISPLAY_NAME="Telemetry Writer"
SA_DESCRIPTION="Writes telemetry events to BigQuery ${DATASET} dataset (least-privilege)"
BQ_ROLE="roles/bigquery.dataEditor"

# Defaults — overridable via flags
KEY_FILE="./telemetry-writer-key.json"
STORE_IN_SECRET_MANAGER=false
DRY_RUN=false
SECRET_NAME="telemetry-writer-key"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Argument parsing ────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --store-in-secret-manager) STORE_IN_SECRET_MANAGER=true ;;
    --key-file)
      if [[ $# -lt 2 || "$2" == -* ]]; then
        echo "Error: --key-file requires a path argument" >&2
        exit 1
      fi
      KEY_FILE="$2"
      shift
      ;;
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
warn()  { echo "  ⚠ $*" >&2; }
err()   { echo "  ✗ $*" >&2; }

print_banner() {
  echo ""
  echo "=================================================="
  echo "  Wrack Telemetry — IAM Setup (PEN-155)"
  echo "=================================================="
  echo "  Project:    ${PROJECT_ID}"
  echo "  Dataset:    ${DATASET}"
  echo "  SA email:   ${SA_EMAIL}"
  echo "  Role:       ${BQ_ROLE} (dataset scope)"
  echo "  Key file:   ${KEY_FILE}"
  [[ "${STORE_IN_SECRET_MANAGER}" == "true" ]] && echo "  Secret Mgr: ${SECRET_NAME}"
  [[ "${DRY_RUN}" == "true" ]]                 && echo "  Mode:       DRY-RUN (no changes)"
  echo "=================================================="
  echo ""
}

# ── Pre-flight checks ───────────────────────────────────────────────────────────
check_prerequisites() {
  # In dry-run mode skip hard failures so the full command sequence is visible.
  if [[ "${DRY_RUN}" == "true" ]]; then
    info "Dry-run: skipping prerequisite validation"
    return
  fi

  local missing=()

  command -v gcloud  &>/dev/null || missing+=(gcloud)
  command -v bq      &>/dev/null || missing+=(bq)
  command -v python3 &>/dev/null || missing+=(python3)

  if [[ ${#missing[@]} -gt 0 ]]; then
    err "Missing required tools: ${missing[*]}"
    err "Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
    exit 1
  fi

  # Verify gcloud is authenticated
  if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | grep -q .; then
    err "No active gcloud account. Run: gcloud auth login"
    exit 1
  fi

  ok "Prerequisites satisfied"
}

# ── Step 1: Set active project ──────────────────────────────────────────────────
set_project() {
  info "Setting active project to ${PROJECT_ID}..."
  run gcloud config set project "${PROJECT_ID}"
  ok "Project set to ${PROJECT_ID}"
}

# ── Step 2: Create service account (idempotent) ────────────────────────────────
create_service_account() {
  info "Creating service account ${SA_NAME}..."

  # Check if it already exists
  if gcloud iam service-accounts describe "${SA_EMAIL}" \
       --project="${PROJECT_ID}" &>/dev/null; then
    ok "Service account ${SA_EMAIL} already exists — skipping creation"
    return
  fi

  run gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="${SA_DISPLAY_NAME}" \
    --description="${SA_DESCRIPTION}" \
    --project="${PROJECT_ID}"

  ok "Service account ${SA_EMAIL} created"
}

# ── Step 3: Grant BigQuery Data Editor on dataset only ─────────────────────────
grant_dataset_iam() {
  info "Granting ${BQ_ROLE} on ${PROJECT_ID}:${DATASET} to ${SA_EMAIL}..."

  local member="serviceAccount:${SA_EMAIL}"
  local tmp_policy
  tmp_policy="$(mktemp /tmp/bq-policy-XXXXXX.json)"
  local updated_policy
  updated_policy="$(mktemp /tmp/bq-policy-updated-XXXXXX.json)"

  # Capture current dataset IAM policy
  run bq get-iam-policy "${PROJECT_ID}:${DATASET}" > "${tmp_policy}" 2>/dev/null || {
    # bq get-iam-policy prints to stdout; if dataset not found, bq exits non-zero
    err "Could not retrieve IAM policy for ${PROJECT_ID}:${DATASET}."
    err "Has PEN-100 (dataset creation) been completed?"
    rm -f "${tmp_policy}" "${updated_policy}"
    exit 1
  }

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] python3 iam_policy_helper.py '${member}' '${BQ_ROLE}' < ${tmp_policy} > ${updated_policy}"
    echo "[DRY-RUN] bq set-iam-policy ${PROJECT_ID}:${DATASET} ${updated_policy}"
    rm -f "${tmp_policy}" "${updated_policy}"
    return
  fi

  # Add binding using the testable Python helper
  python3 "${SCRIPT_DIR}/iam_policy_helper.py" "${member}" "${BQ_ROLE}" \
    < "${tmp_policy}" > "${updated_policy}"

  bq set-iam-policy "${PROJECT_ID}:${DATASET}" "${updated_policy}" \
    > /dev/null

  rm -f "${tmp_policy}" "${updated_policy}"
  ok "${SA_EMAIL} has ${BQ_ROLE} on dataset ${DATASET} (dataset-scoped, not project-wide)"
}

# ── Step 4: Generate service account key ───────────────────────────────────────
generate_key() {
  info "Generating service account key → ${KEY_FILE}..."

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] gcloud iam service-accounts keys create ${KEY_FILE} --iam-account=${SA_EMAIL}"
    return
  fi

  if [[ -f "${KEY_FILE}" ]]; then
    warn "Key file ${KEY_FILE} already exists — rotating key (old file will be overwritten)"
    # Existing key on disk is no longer valid once we create a new one; log its key-id for manual cleanup.
    local old_key_id
    old_key_id="$(python3 -c "import json; d=json.load(open('${KEY_FILE}')); print(d.get('private_key_id','unknown'))")"
    warn "Old key-id ${old_key_id} should be deleted: gcloud iam service-accounts keys delete ${old_key_id} --iam-account=${SA_EMAIL}"
  fi

  gcloud iam service-accounts keys create "${KEY_FILE}" \
    --iam-account="${SA_EMAIL}" \
    --project="${PROJECT_ID}"

  chmod 600 "${KEY_FILE}"
  ok "Key written to ${KEY_FILE} (permissions: 600)"
}

# ── Step 5 (optional): Store key in GCP Secret Manager ─────────────────────────
store_in_secret_manager() {
  [[ "${STORE_IN_SECRET_MANAGER}" != "true" ]] && return

  info "Storing key in Secret Manager as '${SECRET_NAME}'..."

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] gcloud secrets create/update ${SECRET_NAME} --data-file=${KEY_FILE}"
    return
  fi

  if gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
    # Secret exists — add a new version
    run gcloud secrets versions add "${SECRET_NAME}" \
      --data-file="${KEY_FILE}" \
      --project="${PROJECT_ID}"
    ok "New version added to existing secret '${SECRET_NAME}'"
  else
    run gcloud secrets create "${SECRET_NAME}" \
      --data-file="${KEY_FILE}" \
      --replication-policy="automatic" \
      --project="${PROJECT_ID}"
    ok "Secret '${SECRET_NAME}' created in Secret Manager"
  fi
}

# ── Verification ────────────────────────────────────────────────────────────────
verify() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] Skipping verification"
    return
  fi

  info "Verifying service account..."
  gcloud iam service-accounts describe "${SA_EMAIL}" \
    --project="${PROJECT_ID}" \
    --format="value(email,displayName,description)"

  info "Verifying dataset IAM policy contains ${SA_EMAIL}..."
  local member="serviceAccount:${SA_EMAIL}"
  local found
  found="$(bq get-iam-policy "${PROJECT_ID}:${DATASET}" 2>/dev/null \
    | python3 -c "
import json, sys
policy = json.load(sys.stdin)
member = '${member}'
role   = '${BQ_ROLE}'
for b in policy.get('bindings', []):
    if b.get('role') == role and member in b.get('members', []):
        print('found')
        break
")"

  if [[ "${found}" == "found" ]]; then
    ok "IAM binding verified: ${member} → ${BQ_ROLE} on ${DATASET}"
  else
    err "IAM binding NOT found — dataset policy may not have been updated correctly"
    exit 1
  fi
}

# ── Post-run instructions ───────────────────────────────────────────────────────
print_next_steps() {
  echo ""
  echo "=================================================="
  echo "  Setup complete!"
  echo "=================================================="
  echo ""
  echo "IMPORTANT — store the key securely before deleting ${KEY_FILE}:"
  echo ""
  echo "  Option A — GitHub Actions secret (for CI/CD telemetry writes):"
  echo "    1. Copy the JSON key content:"
  echo "         cat ${KEY_FILE}"
  echo "    2. In GitHub: Settings → Secrets → Actions → New repository secret"
  echo "         Name:  TELEMETRY_SA_KEY"
  echo "         Value: <paste JSON content>"
  echo "    3. Delete the local key file:"
  echo "         rm ${KEY_FILE}"
  echo ""
  echo "  Option B — GCP Secret Manager (re-run with --store-in-secret-manager):"
  echo "    bash setup-iam.sh --store-in-secret-manager"
  echo ""
  echo "  Option C — Both (recommended for production):"
  echo "    Do A and B."
  echo ""
  echo "Next telemetry tickets:"
  echo "  PEN-156 — Define shared telemetry event types (shared/telemetry-types/)"
  echo "  PEN-157 — Add telemetry Cloud Function for BigQuery ingestion"
  echo ""
}

# ── Main ────────────────────────────────────────────────────────────────────────
main() {
  print_banner
  check_prerequisites
  set_project
  create_service_account
  grant_dataset_iam
  generate_key
  store_in_secret_manager
  verify
  print_next_steps
}

main
