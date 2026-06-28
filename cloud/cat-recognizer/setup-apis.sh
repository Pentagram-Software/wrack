#!/bin/bash
# setup-apis.sh — Enable required GCP APIs for the CatRecognizer ML pipeline
# PEN-24: Set up GCP project, IAM, and service accounts
#
# Usage:
#   GCP_PROJECT_ID=wrack-control bash setup-apis.sh [options]
#
# Options:
#   --dry-run   Print commands without executing them
#
# APIs enabled:
#   storage.googleapis.com           — Cloud Storage (training data + model artifacts)
#   artifactregistry.googleapis.com  — Artifact Registry (container images for training)
#   containerregistry.googleapis.com — Container Registry (legacy; kept for compatibility)
#
# Prerequisites:
#   gcloud (authenticated, with roles/serviceusage.serviceUsageAdmin on the project)

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-wrack-control}"

DRY_RUN=false

REQUIRED_APIS=(
  "storage.googleapis.com"
  "artifactregistry.googleapis.com"
  "containerregistry.googleapis.com"
)

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

info() { echo "  ▸ $*"; }
ok()   { echo "  ✓ $*"; }
err()  { echo "  ✗ $*" >&2; }

print_banner() {
  echo ""
  echo "=================================================="
  echo "  CatRecognizer — GCP API Setup (PEN-24)"
  echo "=================================================="
  echo "  Project: ${PROJECT_ID}"
  echo "  APIs:    ${REQUIRED_APIS[*]}"
  [[ "${DRY_RUN}" == "true" ]] && echo "  Mode:    DRY-RUN (no changes)"
  echo "=================================================="
  echo ""
}

# ── Pre-flight checks ───────────────────────────────────────────────────────────
check_prerequisites() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    info "Dry-run: skipping prerequisite validation"
    return
  fi

  if ! command -v gcloud &>/dev/null; then
    err "gcloud not found. Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
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

# ── Step 2: Enable APIs ─────────────────────────────────────────────────────────
enable_apis() {
  info "Enabling required APIs..."

  for api in "${REQUIRED_APIS[@]}"; do
    if [[ "${DRY_RUN}" != "true" ]]; then
      if gcloud services list --enabled --filter="name:${api}" \
           --format="value(name)" --project="${PROJECT_ID}" 2>/dev/null | grep -q "${api}"; then
        ok "${api} — already enabled"
        continue
      fi
    fi

    run gcloud services enable "${api}" --project="${PROJECT_ID}"
    [[ "${DRY_RUN}" != "true" ]] && ok "${api} — enabled"
  done
}

# ── Step 3: Verify APIs are enabled ────────────────────────────────────────────
verify_apis() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] Skipping API verification"
    return
  fi

  info "Verifying enabled APIs..."

  local all_ok=true
  for api in "${REQUIRED_APIS[@]}"; do
    if gcloud services list --enabled --filter="name:${api}" \
         --format="value(name)" --project="${PROJECT_ID}" 2>/dev/null | grep -q "${api}"; then
      ok "${api} — confirmed enabled"
    else
      err "${api} — NOT enabled (check gcloud permissions)"
      all_ok=false
    fi
  done

  if [[ "${all_ok}" != "true" ]]; then
    err "One or more APIs could not be verified. Check your permissions and retry."
    exit 1
  fi
}

# ── Post-run instructions ───────────────────────────────────────────────────────
print_next_steps() {
  echo ""
  echo "=================================================="
  echo "  API setup complete!"
  echo "=================================================="
  echo ""
  echo "Next steps:"
  echo "  1. Run setup-iam.sh to create service accounts and GCS buckets:"
  echo "       GCP_PROJECT_ID=${PROJECT_ID} bash cloud/cat-recognizer/setup-iam.sh"
  echo ""
  echo "  2. Smoke-test access after IAM setup:"
  echo "       bash cloud/cat-recognizer/smoke-test.sh"
  echo ""
}

# ── Main ────────────────────────────────────────────────────────────────────────
main() {
  print_banner
  check_prerequisites
  set_project
  enable_apis
  verify_apis
  print_next_steps
}

main
