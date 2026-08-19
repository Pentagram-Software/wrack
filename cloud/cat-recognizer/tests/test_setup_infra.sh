#!/usr/bin/env bash
# Shell tests for cloud/cat-recognizer/setup-infra.sh's idempotency guards
# (review fix for PEN-255–257: bucket/service-account create must not abort
# a re-run under `set -euo pipefail` when the resource already exists).
#
# Run from workspace root:
#   bash cloud/cat-recognizer/tests/test_setup_infra.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAT_RECOGNIZER_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SETUP_SCRIPT="${CAT_RECOGNIZER_DIR}/setup-infra.sh"

FAILURES=0
pass() { echo "  ✓ $*"; }
fail() { echo "  ✗ $*"; FAILURES=$((FAILURES + 1)); }

# ── Mock gcloud ──────────────────────────────────────────────────────────────
# Logs every invocation to CALL_LOG, then reports success/failure per the
# EXISTING_BUCKETS / EXISTING_SAS env vars the test sets before sourcing.
MOCK_BIN_DIR="$(mktemp -d)"
CALL_LOG="$(mktemp)"
cleanup() { rm -rf "${MOCK_BIN_DIR}" "${CALL_LOG}"; }
trap cleanup EXIT

cat > "${MOCK_BIN_DIR}/gcloud" <<'MOCKEOF'
#!/usr/bin/env bash
echo "$*" >> "${CALL_LOG}"
case "$1 $2 $3" in
  "storage buckets describe")
    bucket="${4#gs://}"
    [[ " ${EXISTING_BUCKETS:-} " == *" ${bucket} "* ]] && exit 0 || exit 1
    ;;
  "iam service-accounts describe")
    [[ " ${EXISTING_SAS:-} " == *" $4 "* ]] && exit 0 || exit 1
    ;;
  *) exit 0 ;;  # create / update / cp / add-iam-policy-binding all "succeed"
esac
MOCKEOF
chmod +x "${MOCK_BIN_DIR}/gcloud"
export CALL_LOG
export PATH="${MOCK_BIN_DIR}:${PATH}"

# ── Test 1: existing bucket is skipped, not re-created ──────────────────────
test_skips_create_for_existing_bucket() {
  : > "${CALL_LOG}"
  (
    export GCP_PROJECT_ID="wrack-control"
    export EXISTING_BUCKETS="wrack-control-cat-recognizer-raw-data"
    source "${SETUP_SCRIPT}"
    create_buckets >/dev/null 2>&1
  )
  local creates
  creates="$(grep -c "storage buckets create gs://wrack-control-cat-recognizer-raw-data" "${CALL_LOG}" || true)"
  if [[ "${creates}" -eq 0 ]]; then
    pass "does not call 'buckets create' for an already-existing bucket"
  else
    fail "expected no create call for existing bucket, got ${creates}: $(cat "${CALL_LOG}")"
  fi
}

# ── Test 2: missing bucket is still created ─────────────────────────────────
test_creates_missing_bucket() {
  : > "${CALL_LOG}"
  (
    export GCP_PROJECT_ID="wrack-control"
    export EXISTING_BUCKETS=""
    source "${SETUP_SCRIPT}"
    create_buckets >/dev/null 2>&1
  )
  local creates
  creates="$(grep -c "storage buckets create gs://wrack-control-cat-recognizer-processed-data" "${CALL_LOG}" || true)"
  if [[ "${creates}" -eq 1 ]]; then
    pass "still calls 'buckets create' for a missing bucket"
  else
    fail "expected exactly one create call for missing bucket, got ${creates}"
  fi
}

# ── Test 3: re-running create_buckets twice never aborts (set -euo pipefail) ─
test_rerun_does_not_abort() {
  : > "${CALL_LOG}"
  local rc=0
  (
    export GCP_PROJECT_ID="wrack-control"
    export EXISTING_BUCKETS=""
    source "${SETUP_SCRIPT}"
    create_buckets >/dev/null 2>&1
    export EXISTING_BUCKETS="wrack-control-cat-recognizer-raw-data wrack-control-cat-recognizer-processed-data wrack-control-cat-recognizer-models"
    create_buckets >/dev/null 2>&1  # second run: all now "exist"
  ) || rc=$?
  if [[ "${rc}" -eq 0 ]]; then
    pass "re-running create_buckets after resources exist does not abort"
  else
    fail "second create_buckets run aborted with exit code ${rc}"
  fi
}

# ── Test 4: existing service account is skipped, not re-created ────────────
test_skips_create_for_existing_service_account() {
  : > "${CALL_LOG}"
  (
    export GCP_PROJECT_ID="wrack-control"
    export EXISTING_SAS="cat-recognizer-data-collector@wrack-control.iam.gserviceaccount.com"
    source "${SETUP_SCRIPT}"
    create_service_accounts >/dev/null 2>&1
  )
  local creates
  creates="$(grep -c "iam service-accounts create cat-recognizer-data-collector" "${CALL_LOG}" || true)"
  if [[ "${creates}" -eq 0 ]]; then
    pass "does not call 'service-accounts create' for an already-existing SA"
  else
    fail "expected no create call for existing SA, got ${creates}"
  fi
}

# ── Test 5: missing service account is still created ────────────────────────
test_creates_missing_service_account() {
  : > "${CALL_LOG}"
  (
    export GCP_PROJECT_ID="wrack-control"
    export EXISTING_SAS=""
    source "${SETUP_SCRIPT}"
    create_service_accounts >/dev/null 2>&1
  )
  local creates
  creates="$(grep -c "iam service-accounts create cat-recognizer-trainer-export" "${CALL_LOG}" || true)"
  if [[ "${creates}" -eq 1 ]]; then
    pass "still calls 'service-accounts create' for a missing SA"
  else
    fail "expected exactly one create call for missing SA, got ${creates}"
  fi
}

echo "Running setup-infra.sh idempotency tests…"
test_skips_create_for_existing_bucket
test_creates_missing_bucket
test_rerun_does_not_abort
test_skips_create_for_existing_service_account
test_creates_missing_service_account

if [[ "${FAILURES}" -eq 0 ]]; then
  echo "All tests passed."
  exit 0
fi
echo "${FAILURES} test(s) failed."
exit 1
