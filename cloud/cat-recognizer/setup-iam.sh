#!/bin/bash
# setup-iam.sh — Create GCS buckets and service accounts for the CatRecognizer ML pipeline
# PEN-25: Provision GCS buckets and structure (three-bucket layout)
#
# Usage:
#   GCP_PROJECT_ID=wrack-control bash setup-iam.sh [options]
#
# Options:
#   --key-dir PATH              Directory to write JSON keys (default: ./keys)
#   --store-in-secret-manager   Also store generated keys in GCP Secret Manager
#   --dry-run                   Print commands without executing them
#   --skip-buckets              Skip GCS bucket creation, lifecycle, and folder structure (IAM only)
#
# Resources created:
#
#   GCS Buckets (region: europe-west3):
#     <PROJECT>-cat-recognizer-raw-data        — raw captured frames per cat (90-day auto-delete)
#     <PROJECT>-cat-recognizer-processed-data  — train/val/test splits and annotations
#     <PROJECT>-cat-recognizer-models          — exported ONNX model artifacts
#
#   Folder structure (zero-byte .keep placeholders):
#     raw-data:       ryfka/.keep  chaja/.keep  lea/.keep
#     processed-data: train/.keep  val/.keep    test/.keep
#
#   Service Accounts:
#     cat-recognizer-data@<PROJECT>.iam.gserviceaccount.com
#       roles/storage.objectAdmin  on raw-data bucket       (upload + manage frames)
#       roles/storage.objectViewer on processed-data bucket (read annotations)
#
#     cat-recognizer-trainer@<PROJECT>.iam.gserviceaccount.com
#       roles/storage.objectViewer on raw-data bucket       (read frames for training)
#       roles/storage.objectAdmin  on processed-data bucket (write splits/annotations)
#       roles/storage.objectAdmin  on models bucket         (write model artifacts)
#       roles/artifactregistry.writer on cat-recognizer repo (push container images)
#
# Prerequisites:
#   gcloud (authenticated, with roles/iam.serviceAccountAdmin,
#           roles/storage.admin, roles/artifactregistry.admin)

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-wrack-control}"
REGION="europe-west3"
AR_LOCATION="europe-west3"

# GCS bucket names (must be globally unique — using project prefix)
BUCKET_RAW="${PROJECT_ID}-cat-recognizer-raw-data"
BUCKET_PROCESSED="${PROJECT_ID}-cat-recognizer-processed-data"
BUCKET_MODELS="${PROJECT_ID}-cat-recognizer-models"

# Artifact Registry repository
AR_REPO="cat-recognizer"
AR_FORMAT="DOCKER"

# Service accounts
SA_DATA_NAME="cat-recognizer-data"
SA_DATA_DISPLAY="CatRecognizer Data Collector"
SA_DATA_DESC="Uploads raw frames to GCS ${BUCKET_RAW}; reads processed data (least-privilege)"

SA_TRAINER_NAME="cat-recognizer-trainer"
SA_TRAINER_DISPLAY="CatRecognizer Trainer"
SA_TRAINER_DESC="Reads raw data, writes processed data and model artifacts; pushes container images (least-privilege)"

# Defaults — overridable via flags
KEY_DIR="./keys"
STORE_IN_SECRET_MANAGER=false
DRY_RUN=false
SKIP_BUCKETS=false

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Argument parsing ────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --store-in-secret-manager) STORE_IN_SECRET_MANAGER=true ;;
    --skip-buckets) SKIP_BUCKETS=true ;;
    --key-dir)
      if [[ $# -lt 2 || "$2" == -* ]]; then
        echo "Error: --key-dir requires a path argument" >&2
        exit 1
      fi
      KEY_DIR="$2"
      shift
      ;;
    --dry-run) DRY_RUN=true ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

SA_DATA_EMAIL="${SA_DATA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SA_TRAINER_EMAIL="${SA_TRAINER_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

KEY_DATA="${KEY_DIR}/${SA_DATA_NAME}-key.json"
KEY_TRAINER="${KEY_DIR}/${SA_TRAINER_NAME}-key.json"

# ── Helpers ─────────────────────────────────────────────────────────────────────
run() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] $*"
  else
    "$@"
  fi
}

info() { echo "  ▸ $*"; }
ok()   { echo "  ✓ $*"; }
warn() { echo "  ⚠ $*" >&2; }
err()  { echo "  ✗ $*" >&2; }

print_banner() {
  echo ""
  echo "=================================================="
  echo "  CatRecognizer — IAM Setup (PEN-25)"
  echo "=================================================="
  echo "  Project:           ${PROJECT_ID}"
  echo "  Region:            ${REGION}"
  echo "  Bucket raw:        ${BUCKET_RAW}"
  echo "  Bucket processed:  ${BUCKET_PROCESSED}"
  echo "  Bucket models:     ${BUCKET_MODELS}"
  echo "  SA data:           ${SA_DATA_EMAIL}"
  echo "  SA trainer:        ${SA_TRAINER_EMAIL}"
  echo "  Key dir:           ${KEY_DIR}"
  [[ "${STORE_IN_SECRET_MANAGER}" == "true" ]] && echo "  Secret Mgr:        enabled"
  [[ "${DRY_RUN}" == "true" ]] && echo "  Mode:              DRY-RUN (no changes)"
  echo "=================================================="
  echo ""
}

# ── Pre-flight checks ───────────────────────────────────────────────────────────
check_prerequisites() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    info "Dry-run: skipping prerequisite validation"
    return
  fi

  local missing=()
  command -v gcloud &>/dev/null || missing+=(gcloud)

  if [[ ${#missing[@]} -gt 0 ]]; then
    err "Missing required tools: ${missing[*]}"
    err "Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
    exit 1
  fi

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

# ── Step 2: Create GCS buckets ──────────────────────────────────────────────────
create_buckets() {
  if [[ "${SKIP_BUCKETS}" == "true" ]]; then
    info "Skipping bucket creation (--skip-buckets)"
    return
  fi

  for bucket in "${BUCKET_RAW}" "${BUCKET_PROCESSED}" "${BUCKET_MODELS}"; do
    info "Creating GCS bucket gs://${bucket}..."

    if [[ "${DRY_RUN}" != "true" ]]; then
      if gcloud storage buckets describe "gs://${bucket}" \
           --project="${PROJECT_ID}" &>/dev/null; then
        ok "Bucket gs://${bucket} already exists — skipping creation"
        continue
      fi
    fi

    run gcloud storage buckets create "gs://${bucket}" \
      --project="${PROJECT_ID}" \
      --location="${REGION}" \
      --uniform-bucket-level-access \
      --public-access-prevention

    [[ "${DRY_RUN}" != "true" ]] && ok "Bucket gs://${bucket} created (${REGION}, uniform IAM, no public access)"
  done
}

# ── Step 3: Apply lifecycle rule to raw-data bucket ────────────────────────────
apply_lifecycle() {
  if [[ "${SKIP_BUCKETS}" == "true" ]]; then
    info "Skipping lifecycle rule (--skip-buckets)"
    return
  fi

  local lifecycle_file="${SCRIPT_DIR}/lifecycle-raw-data.json"

  if [[ ! -f "${lifecycle_file}" ]] && [[ "${DRY_RUN}" != "true" ]]; then
    err "Lifecycle config file not found: ${lifecycle_file}"
    exit 1
  fi

  info "Applying 90-day auto-delete lifecycle rule to gs://${BUCKET_RAW}..."
  run gcloud storage buckets update "gs://${BUCKET_RAW}" \
    --lifecycle-file="${lifecycle_file}" \
    --project="${PROJECT_ID}"
  [[ "${DRY_RUN}" != "true" ]] && ok "90-day auto-delete lifecycle applied to gs://${BUCKET_RAW}"
}

# ── Step 4: Create service accounts (idempotent) ───────────────────────────────
create_service_account() {
  local name="$1" email="$2" display="$3" description="$4"

  info "Creating service account ${name}..."

  if [[ "${DRY_RUN}" != "true" ]]; then
    if gcloud iam service-accounts describe "${email}" \
         --project="${PROJECT_ID}" &>/dev/null; then
      ok "Service account ${email} already exists — skipping creation"
      return
    fi
  fi

  run gcloud iam service-accounts create "${name}" \
    --display-name="${display}" \
    --description="${description}" \
    --project="${PROJECT_ID}"

  [[ "${DRY_RUN}" != "true" ]] && ok "Service account ${email} created"
}

create_service_accounts() {
  create_service_account \
    "${SA_DATA_NAME}" "${SA_DATA_EMAIL}" \
    "${SA_DATA_DISPLAY}" "${SA_DATA_DESC}"

  create_service_account \
    "${SA_TRAINER_NAME}" "${SA_TRAINER_EMAIL}" \
    "${SA_TRAINER_DISPLAY}" "${SA_TRAINER_DESC}"
}

# ── Step 5: Grant bucket-level IAM roles ───────────────────────────────────────
grant_bucket_iam() {
  if [[ "${SKIP_BUCKETS}" == "true" ]]; then
    info "Skipping bucket IAM (--skip-buckets)"
    return
  fi

  # cat-recognizer-data: objectAdmin on raw-data bucket (upload + manage frames)
  info "Granting roles/storage.objectAdmin on ${BUCKET_RAW} to ${SA_DATA_EMAIL}..."
  run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_RAW}" \
    --member="serviceAccount:${SA_DATA_EMAIL}" \
    --role="roles/storage.objectAdmin" \
    --project="${PROJECT_ID}"
  [[ "${DRY_RUN}" != "true" ]] && ok "${SA_DATA_EMAIL} → roles/storage.objectAdmin on ${BUCKET_RAW}"

  # cat-recognizer-data: objectViewer on processed-data bucket (read annotations)
  info "Granting roles/storage.objectViewer on ${BUCKET_PROCESSED} to ${SA_DATA_EMAIL}..."
  run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_PROCESSED}" \
    --member="serviceAccount:${SA_DATA_EMAIL}" \
    --role="roles/storage.objectViewer" \
    --project="${PROJECT_ID}"
  [[ "${DRY_RUN}" != "true" ]] && ok "${SA_DATA_EMAIL} → roles/storage.objectViewer on ${BUCKET_PROCESSED}"

  # cat-recognizer-trainer: objectViewer on raw-data bucket (read frames for training)
  info "Granting roles/storage.objectViewer on ${BUCKET_RAW} to ${SA_TRAINER_EMAIL}..."
  run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_RAW}" \
    --member="serviceAccount:${SA_TRAINER_EMAIL}" \
    --role="roles/storage.objectViewer" \
    --project="${PROJECT_ID}"
  [[ "${DRY_RUN}" != "true" ]] && ok "${SA_TRAINER_EMAIL} → roles/storage.objectViewer on ${BUCKET_RAW}"

  # cat-recognizer-trainer: objectAdmin on processed-data bucket (write splits/annotations)
  info "Granting roles/storage.objectAdmin on ${BUCKET_PROCESSED} to ${SA_TRAINER_EMAIL}..."
  run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_PROCESSED}" \
    --member="serviceAccount:${SA_TRAINER_EMAIL}" \
    --role="roles/storage.objectAdmin" \
    --project="${PROJECT_ID}"
  [[ "${DRY_RUN}" != "true" ]] && ok "${SA_TRAINER_EMAIL} → roles/storage.objectAdmin on ${BUCKET_PROCESSED}"

  # cat-recognizer-trainer: objectAdmin on models bucket (write model artifacts)
  info "Granting roles/storage.objectAdmin on ${BUCKET_MODELS} to ${SA_TRAINER_EMAIL}..."
  run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_MODELS}" \
    --member="serviceAccount:${SA_TRAINER_EMAIL}" \
    --role="roles/storage.objectAdmin" \
    --project="${PROJECT_ID}"
  [[ "${DRY_RUN}" != "true" ]] && ok "${SA_TRAINER_EMAIL} → roles/storage.objectAdmin on ${BUCKET_MODELS}"
}

# ── Step 6: Create Artifact Registry repo + grant writer role ──────────────────
setup_artifact_registry() {
  info "Creating Artifact Registry repository '${AR_REPO}' (${AR_FORMAT})..."

  if [[ "${DRY_RUN}" != "true" ]]; then
    if gcloud artifacts repositories describe "${AR_REPO}" \
         --location="${AR_LOCATION}" \
         --project="${PROJECT_ID}" &>/dev/null; then
      ok "Artifact Registry repo '${AR_REPO}' already exists — skipping creation"
    else
      run gcloud artifacts repositories create "${AR_REPO}" \
        --repository-format="${AR_FORMAT}" \
        --location="${AR_LOCATION}" \
        --description="CatRecognizer training container images" \
        --project="${PROJECT_ID}"
      ok "Artifact Registry repo '${AR_REPO}' created (${AR_LOCATION})"
    fi
  else
    run gcloud artifacts repositories create "${AR_REPO}" \
      --repository-format="${AR_FORMAT}" \
      --location="${AR_LOCATION}" \
      --description="CatRecognizer training container images" \
      --project="${PROJECT_ID}"
  fi

  # Grant roles/artifactregistry.writer to trainer SA
  info "Granting roles/artifactregistry.writer on ${AR_REPO} to ${SA_TRAINER_EMAIL}..."
  run gcloud artifacts repositories add-iam-policy-binding "${AR_REPO}" \
    --location="${AR_LOCATION}" \
    --member="serviceAccount:${SA_TRAINER_EMAIL}" \
    --role="roles/artifactregistry.writer" \
    --project="${PROJECT_ID}"
  [[ "${DRY_RUN}" != "true" ]] && ok "${SA_TRAINER_EMAIL} → roles/artifactregistry.writer on ${AR_REPO}"
}

# ── Step 7: Upload zero-byte .keep placeholder (idempotent) ────────────────────
_upload_keep() {
  local bucket="$1" prefix="$2"
  local object="gs://${bucket}/${prefix}/.keep"

  info "Ensuring placeholder ${object}..."

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] gcloud storage cp <empty-file> ${object} --content-type=text/plain --project=${PROJECT_ID}"
    return
  fi

  if gcloud storage objects describe "${object}" --project="${PROJECT_ID}" &>/dev/null; then
    ok "${object} already exists — skipping"
    return
  fi

  local tmp_file
  tmp_file="$(mktemp)"
  trap "rm -f ${tmp_file}" RETURN
  gcloud storage cp "${tmp_file}" "${object}" \
    --content-type="text/plain" \
    --project="${PROJECT_ID}"
  ok "Created ${object}"
}

# ── Step 8: Initialise folder structure with .keep placeholders ────────────────
create_folder_structure() {
  if [[ "${SKIP_BUCKETS}" == "true" ]]; then
    info "Skipping folder structure (--skip-buckets)"
    return
  fi

  echo ""
  echo "  ── Folder structure ───────────────────────────────────────────────"

  # raw-data bucket: one subfolder per cat
  for prefix in ryfka chaja lea; do
    _upload_keep "${BUCKET_RAW}" "${prefix}"
  done

  # processed-data bucket: train/val/test splits
  for prefix in train val test; do
    _upload_keep "${BUCKET_PROCESSED}" "${prefix}"
  done
}

# ── Step 9: Generate service account keys ──────────────────────────────────────
generate_key() {
  local email="$1" key_file="$2" secret_name="$3"

  info "Generating key for ${email} → ${key_file}..."

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] mkdir -p $(dirname "${key_file}")"
    echo "[DRY-RUN] gcloud iam service-accounts keys create ${key_file} --iam-account=${email}"
    return
  fi

  mkdir -p "$(dirname "${key_file}")"

  if [[ -f "${key_file}" ]]; then
    local old_key_id
    old_key_id="$(python3 -c "import json; d=json.load(open('${key_file}')); print(d.get('private_key_id','unknown'))")"
    warn "Key file ${key_file} already exists (key-id: ${old_key_id}) — rotating"
    warn "After rotation, delete old key: gcloud iam service-accounts keys delete ${old_key_id} --iam-account=${email}"
  fi

  gcloud iam service-accounts keys create "${key_file}" \
    --iam-account="${email}" \
    --project="${PROJECT_ID}"

  chmod 600 "${key_file}"
  ok "Key written to ${key_file} (permissions: 600)"

  if [[ "${STORE_IN_SECRET_MANAGER}" == "true" ]]; then
    store_secret "${secret_name}" "${key_file}"
  fi
}

generate_keys() {
  generate_key "${SA_DATA_EMAIL}"    "${KEY_DATA}"    "cat-recognizer-data-key"
  generate_key "${SA_TRAINER_EMAIL}" "${KEY_TRAINER}" "cat-recognizer-trainer-key"
}

# ── Step 10 (optional): Store key in GCP Secret Manager ─────────────────────────
store_secret() {
  local secret_name="$1" key_file="$2"

  info "Storing key in Secret Manager as '${secret_name}'..."

  if gcloud secrets describe "${secret_name}" --project="${PROJECT_ID}" &>/dev/null; then
    run gcloud secrets versions add "${secret_name}" \
      --data-file="${key_file}" \
      --project="${PROJECT_ID}"
    ok "New version added to existing secret '${secret_name}'"
  else
    run gcloud secrets create "${secret_name}" \
      --data-file="${key_file}" \
      --replication-policy="automatic" \
      --project="${PROJECT_ID}"
    ok "Secret '${secret_name}' created in Secret Manager"
  fi
}

# ── Verification ────────────────────────────────────────────────────────────────
verify() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] Skipping verification"
    return
  fi

  echo ""
  echo "── Verification ──────────────────────────────────────────────────────"

  for email in "${SA_DATA_EMAIL}" "${SA_TRAINER_EMAIL}"; do
    info "Verifying service account ${email}..."
    gcloud iam service-accounts describe "${email}" \
      --project="${PROJECT_ID}" \
      --format="value(email,displayName)" 2>/dev/null \
    && ok "${email} — confirmed" \
    || { err "${email} — NOT found"; }
  done

  if [[ "${SKIP_BUCKETS}" != "true" ]]; then
    for bucket in "${BUCKET_RAW}" "${BUCKET_PROCESSED}" "${BUCKET_MODELS}"; do
      info "Verifying bucket gs://${bucket}..."
      gcloud storage buckets describe "gs://${bucket}" \
        --project="${PROJECT_ID}" \
        --format="value(name)" &>/dev/null \
      && ok "gs://${bucket} — confirmed" \
      || err "gs://${bucket} — NOT found"
    done
  fi

  info "Verifying Artifact Registry repo '${AR_REPO}'..."
  gcloud artifacts repositories describe "${AR_REPO}" \
    --location="${AR_LOCATION}" \
    --project="${PROJECT_ID}" \
    --format="value(name)" &>/dev/null \
  && ok "Artifact Registry repo '${AR_REPO}' (${AR_LOCATION}) — confirmed" \
  || err "Artifact Registry repo '${AR_REPO}' — NOT found"
}

# ── Post-run instructions ───────────────────────────────────────────────────────
print_next_steps() {
  echo ""
  echo "=================================================="
  echo "  IAM setup complete!"
  echo "=================================================="
  echo ""
  echo "IMPORTANT — store keys securely before deleting from ${KEY_DIR}/:"
  echo ""
  echo "  Option A — GitHub Actions secrets (for CI/CD training runs):"
  echo "    cat ${KEY_DATA}    → secret name: CAT_RECOGNIZER_DATA_SA_KEY"
  echo "    cat ${KEY_TRAINER} → secret name: CAT_RECOGNIZER_TRAINER_SA_KEY"
  echo "    GitHub: Settings → Secrets → Actions → New repository secret"
  echo "    Then: rm ${KEY_DATA} ${KEY_TRAINER}"
  echo ""
  echo "  Option B — GCP Secret Manager (already done if --store-in-secret-manager was set):"
  echo "    Re-run with --store-in-secret-manager to store/rotate."
  echo ""
  echo "  Option C — Both (recommended for production)"
  echo ""
  echo "Run the smoke test to verify end-to-end access:"
  echo "  GOOGLE_APPLICATION_CREDENTIALS=${KEY_DATA} \\"
  echo "    python3 cloud/cat-recognizer/smoke_test.py \\"
  echo "    --bucket-raw=${BUCKET_RAW} --bucket-processed=${BUCKET_PROCESSED} --mode=data"
  echo ""
  echo "  GOOGLE_APPLICATION_CREDENTIALS=${KEY_TRAINER} \\"
  echo "    python3 cloud/cat-recognizer/smoke_test.py \\"
  echo "    --bucket-raw=${BUCKET_RAW} --bucket-processed=${BUCKET_PROCESSED} \\"
  echo "    --bucket-models=${BUCKET_MODELS} --mode=trainer"
  echo ""
}

# ── Main ────────────────────────────────────────────────────────────────────────
main() {
  print_banner
  check_prerequisites
  set_project
  create_buckets
  apply_lifecycle
  create_service_accounts
  grant_bucket_iam
  setup_artifact_registry
  create_folder_structure
  generate_keys
  verify
  print_next_steps
}

main
