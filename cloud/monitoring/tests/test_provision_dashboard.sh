#!/bin/bash
# Shell-level regression tests for cloud/monitoring/provision-dashboard.sh
#
# Complements the pytest suites for write_dashboard_credentials.py and
# build_dashboard_request.py (JSON-assembly logic in isolation) by covering
# the two subcommands' end-to-end shell behavior: dry-run validation, the
# Secret Manager create/update branch, the actual curl POST, and scratch-file
# cleanup -- mirroring test_setup_grafana_secret.sh's approach of faking
# `gcloud`/`curl` on PATH so this never touches real GCP or Grafana Cloud.
#
# Run from workspace root:
#   bash cloud/monitoring/tests/test_provision_dashboard.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITORING_DIR="$(dirname "${SCRIPT_DIR}")"
SCRIPT="${MONITORING_DIR}/provision-dashboard.sh"
DASHBOARD_FILE="${MONITORING_DIR}/dashboards/wrack-ev3-health.json"

FAILURES=0
pass() { echo "  ✓ $*"; }
fail() { echo "  ✗ $*"; FAILURES=$((FAILURES + 1)); }

TEST_TMP_DIR="$(mktemp -d)"
FAKE_BIN_DIR="$(mktemp -d)"

cleanup_all() {
  rm -rf "${TEST_TMP_DIR}" "${FAKE_BIN_DIR}"
}
trap cleanup_all EXIT

# Extract a "-> <path>..." scratch-file path from a captured run's stdout
# (both reserve_creds_file's store-credentials and provision log lines end
# with this shape).
extract_scratch_path() {
  grep -oE '→ [^ ]*\.\.\.$' "$1" 2>/dev/null \
    | tail -n1 \
    | sed -E 's/→ (.*)\.\.\.$/\1/'
}

# Fake gcloud: enough surface for provision-dashboard.sh's two subcommands.
# "secrets versions access" echoes FAKE_CREDS_JSON (a dashboard-credentials
# blob) so the provision subcommand has something to parse.
cat > "${FAKE_BIN_DIR}/gcloud" <<'FAKE_GCLOUD'
#!/bin/bash
case "$*" in
  "auth list"*) echo "fake@example.com"; exit 0 ;;
  "secrets describe"*)
    if [[ "${FAKE_GCLOUD_DESCRIBE_SUCCEEDS:-}" == "1" ]]; then
      exit 0
    fi
    echo "${FAKE_GCLOUD_DESCRIBE_ERROR:-ERROR: (gcloud.secrets.describe) NOT_FOUND: Secret not found.}" >&2
    exit 1
    ;;
  "secrets create"*)
    for arg in "$@"; do
      case "${arg}" in
        --data-file=*)
          [[ -n "${CAPTURE_FILE:-}" ]] && cp "${arg#--data-file=}" "${CAPTURE_FILE}"
          ;;
      esac
    done
    exit 0
    ;;
  "secrets versions add"*)
    for arg in "$@"; do
      case "${arg}" in
        --data-file=*)
          [[ -n "${CAPTURE_FILE:-}" ]] && cp "${arg#--data-file=}" "${CAPTURE_FILE}"
          ;;
      esac
    done
    exit 0
    ;;
  "secrets versions describe"*) echo "ENABLED"; exit 0 ;;
  "secrets versions access latest"*)
    if [[ -n "${FAKE_CREDS_JSON:-}" ]]; then
      echo "${FAKE_CREDS_JSON}"
    else
      echo '{"grafana_url": "https://fake.grafana.net", "token": "fake-token"}'
    fi
    exit 0
    ;;
  *) echo "unhandled fake gcloud call: $*" >&2; exit 1 ;;
esac
FAKE_GCLOUD
chmod +x "${FAKE_BIN_DIR}/gcloud"

# Fake curl: records every arg it was called with (CAPTURE_CURL_ARGS) and the
# contents of the --data-binary @<file> request body (CAPTURE_CURL_BODY), then
# emits a body + trailing HTTP status line the way `curl -w '\n%{http_code}'`
# does. FAKE_CURL_HTTP_CODE controls the simulated response status.
cat > "${FAKE_BIN_DIR}/curl" <<'FAKE_CURL'
#!/bin/bash
[[ -n "${CAPTURE_CURL_ARGS:-}" ]] && printf '%s\n' "$@" > "${CAPTURE_CURL_ARGS}"
for arg in "$@"; do
  case "${arg}" in
    --data-binary=*|@*)
      body_ref="${arg#@}"
      body_ref="${body_ref#--data-binary=}"
      [[ -n "${CAPTURE_CURL_BODY:-}" && -f "${body_ref}" ]] && cp "${body_ref}" "${CAPTURE_CURL_BODY}"
      ;;
  esac
done
echo '{"id": 1, "status": "success"}'
echo "${FAKE_CURL_HTTP_CODE:-200}"
FAKE_CURL
chmod +x "${FAKE_BIN_DIR}/curl"

# -- store-credentials: dry-run validates required inputs --------------------
test_store_credentials_dry_run_requires_inputs() {
  local out="${TEST_TMP_DIR}/store-dry-no-inputs.out"
  PATH="/usr/bin:/bin" bash "${SCRIPT}" store-credentials --dry-run > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -ne 0 ]] && grep -q "Missing required inputs" "${out}"; then
    pass "store-credentials --dry-run with no inputs fails validation"
  else
    fail "expected store-credentials --dry-run with no inputs to fail validation (rc=${rc})"
  fi
}

# -- store-credentials: dry-run with inputs succeeds without touching gcloud -
test_store_credentials_dry_run_with_inputs_succeeds() {
  local out="${TEST_TMP_DIR}/store-dry-with-inputs.out"
  PATH="/usr/bin:/bin" GRAFANA_DASHBOARD_TOKEN="faketoken" \
    bash "${SCRIPT}" store-credentials --grafana-url https://wrack.grafana.net --dry-run \
    > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -eq 0 ]] && grep -q "DRY-RUN" "${out}"; then
    pass "store-credentials --dry-run with required inputs succeeds without gcloud/curl on PATH"
  else
    fail "expected store-credentials --dry-run with inputs to succeed (rc=${rc})"
  fi
}

# -- store-credentials: creates a new secret when none exists ----------------
test_store_credentials_creates_when_not_found() {
  local out="${TEST_TMP_DIR}/store-create.out"
  local cap="${TEST_TMP_DIR}/store-create.captured.json"
  rm -f "${cap}"

  PATH="${FAKE_BIN_DIR}:${PATH}" CAPTURE_FILE="${cap}" GRAFANA_DASHBOARD_TOKEN="faketoken" \
    bash "${SCRIPT}" store-credentials --grafana-url https://wrack.grafana.net \
    > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -eq 0 ]] && grep -q "created in Secret Manager" "${out}" \
     && grep -q '"grafana_url": "https://wrack.grafana.net"' "${cap}" \
     && grep -q '"token": "faketoken"' "${cap}"; then
    pass "store-credentials creates a new secret with the expected JSON payload when none exists"
  else
    fail "expected store-credentials to create a new secret (rc=${rc})"
  fi
}

# -- store-credentials: adds a version when the secret already exists -------
test_store_credentials_adds_version_when_exists() {
  local out="${TEST_TMP_DIR}/store-update.out"

  PATH="${FAKE_BIN_DIR}:${PATH}" GRAFANA_DASHBOARD_TOKEN="faketoken" \
    FAKE_GCLOUD_DESCRIBE_SUCCEEDS="1" \
    bash "${SCRIPT}" store-credentials --grafana-url https://wrack.grafana.net \
    > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -eq 0 ]] && grep -q "New version added to existing secret" "${out}"; then
    pass "store-credentials adds a new version when the secret already exists"
  else
    fail "expected store-credentials to add a version to an existing secret (rc=${rc})"
  fi
}

# -- store-credentials: scratch file is cleaned up after a successful run ----
test_store_credentials_cleans_up_scratch_file() {
  local out="${TEST_TMP_DIR}/store-cleanup.out"

  PATH="${FAKE_BIN_DIR}:${PATH}" GRAFANA_DASHBOARD_TOKEN="faketoken" \
    bash "${SCRIPT}" store-credentials --grafana-url https://wrack.grafana.net \
    > "${out}" 2>&1

  local scratch_file
  scratch_file="$(extract_scratch_path "${out}")"

  if [[ -n "${scratch_file}" && ! -f "${scratch_file}" ]]; then
    pass "store-credentials cleans up its scratch credentials file after a successful run"
  else
    fail "expected the scratch credentials file (${scratch_file}) to be removed after success"
    [[ -n "${scratch_file}" ]] && rm -f "${scratch_file}"
  fi
}

# -- provision: dry-run validates the dashboard file without touching gcloud -
test_provision_dry_run_validates_dashboard() {
  local out="${TEST_TMP_DIR}/provision-dry-run.out"
  PATH="/usr/bin:/bin" bash "${SCRIPT}" provision --dashboard-file "${DASHBOARD_FILE}" --dry-run \
    > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -eq 0 ]] && grep -q "valid JSON" "${out}" && grep -q "DRY-RUN" "${out}"; then
    pass "provision --dry-run validates the dashboard JSON without gcloud/curl on PATH"
  else
    fail "expected provision --dry-run to succeed and validate the dashboard file (rc=${rc})"
  fi
}

# -- provision: dry-run fails fast on a missing dashboard file ---------------
test_provision_dry_run_fails_on_missing_dashboard() {
  local out="${TEST_TMP_DIR}/provision-dry-run-missing.out"
  PATH="/usr/bin:/bin" bash "${SCRIPT}" provision \
    --dashboard-file "${TEST_TMP_DIR}/does-not-exist.json" --dry-run \
    > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -ne 0 ]] && grep -q "not found" "${out}"; then
    pass "provision --dry-run fails fast on a missing dashboard file"
  else
    fail "expected provision --dry-run to fail on a missing dashboard file (rc=${rc})"
  fi
}

# -- provision: dry-run fails fast on invalid JSON ---------------------------
test_provision_dry_run_fails_on_invalid_json() {
  local bad_file="${TEST_TMP_DIR}/bad.json"
  echo "{not valid json" > "${bad_file}"

  local out="${TEST_TMP_DIR}/provision-dry-run-invalid.out"
  PATH="/usr/bin:/bin" bash "${SCRIPT}" provision --dashboard-file "${bad_file}" --dry-run \
    > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -ne 0 ]] && grep -q "not valid JSON" "${out}"; then
    pass "provision --dry-run fails fast on a dashboard file that isn't valid JSON"
  else
    fail "expected provision --dry-run to fail on invalid JSON (rc=${rc})"
  fi
}

# -- provision: fetches credentials, POSTs the dashboard, reports success ----
test_provision_posts_dashboard_on_success() {
  local out="${TEST_TMP_DIR}/provision-success.out"
  local body_cap="${TEST_TMP_DIR}/provision-success.body.json"
  local args_cap="${TEST_TMP_DIR}/provision-success.args.txt"

  PATH="${FAKE_BIN_DIR}:${PATH}" CAPTURE_CURL_BODY="${body_cap}" CAPTURE_CURL_ARGS="${args_cap}" \
    FAKE_CREDS_JSON='{"grafana_url": "https://wrack.grafana.net", "token": "prov-token"}' \
    bash "${SCRIPT}" provision --dashboard-file "${DASHBOARD_FILE}" \
    > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -eq 0 ]] \
     && grep -q "provisioned successfully" "${out}" \
     && grep -q "https://wrack.grafana.net/api/dashboards/db" "${args_cap}" \
     && grep -q "Bearer prov-token" "${args_cap}" \
     && grep -q '"overwrite": true' "${body_cap}" \
     && grep -q "wrack-ev3-health" "${body_cap}"; then
    pass "provision fetches credentials, POSTs the wrapped dashboard, and reports success"
  else
    fail "expected provision to POST the dashboard with the fetched credentials (rc=${rc})"
  fi
}

# -- provision: a non-200 response is treated as failure ---------------------
test_provision_fails_on_non_200_response() {
  local out="${TEST_TMP_DIR}/provision-failure.out"

  PATH="${FAKE_BIN_DIR}:${PATH}" FAKE_CURL_HTTP_CODE="401" \
    bash "${SCRIPT}" provision --dashboard-file "${DASHBOARD_FILE}" \
    > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -ne 0 ]] && grep -q "Provisioning failed" "${out}" && grep -q "401" "${out}"; then
    pass "provision treats a non-200 response as a failure"
  else
    fail "expected provision to fail on a non-200 response (rc=${rc})"
  fi
}

# -- provision: scratch files are cleaned up after a run ----------------------
test_provision_cleans_up_scratch_files() {
  local out="${TEST_TMP_DIR}/provision-cleanup.out"

  PATH="${FAKE_BIN_DIR}:${PATH}" \
    bash "${SCRIPT}" provision --dashboard-file "${DASHBOARD_FILE}" \
    > "${out}" 2>&1

  local creds_scratch
  creds_scratch="$(extract_scratch_path "${out}")"

  if [[ -n "${creds_scratch}" && ! -f "${creds_scratch}" ]]; then
    pass "provision cleans up its scratch credentials file after a run"
  else
    fail "expected the scratch credentials file (${creds_scratch}) to be removed after the run"
    [[ -n "${creds_scratch}" ]] && rm -f "${creds_scratch}"
  fi
}

# -- subcommand handling -------------------------------------------------------
test_missing_subcommand_fails() {
  local out="${TEST_TMP_DIR}/no-subcommand.out"
  bash "${SCRIPT}" > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -ne 0 ]] && grep -q "Missing required subcommand" "${out}"; then
    pass "running with no subcommand fails with a clear message"
  else
    fail "expected no-subcommand invocation to fail with a clear message (rc=${rc})"
  fi
}

test_unknown_subcommand_fails() {
  local out="${TEST_TMP_DIR}/bad-subcommand.out"
  bash "${SCRIPT}" nonsense > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -ne 0 ]] && grep -q "Unknown subcommand" "${out}"; then
    pass "an unknown subcommand fails with a clear message"
  else
    fail "expected an unknown subcommand to fail with a clear message (rc=${rc})"
  fi
}

echo "Running shell-level regression tests for provision-dashboard.sh..."
echo ""
test_store_credentials_dry_run_requires_inputs
test_store_credentials_dry_run_with_inputs_succeeds
test_store_credentials_creates_when_not_found
test_store_credentials_adds_version_when_exists
test_store_credentials_cleans_up_scratch_file
test_provision_dry_run_validates_dashboard
test_provision_dry_run_fails_on_missing_dashboard
test_provision_dry_run_fails_on_invalid_json
test_provision_posts_dashboard_on_success
test_provision_fails_on_non_200_response
test_provision_cleans_up_scratch_files
test_missing_subcommand_fails
test_unknown_subcommand_fails
echo ""

if [[ ${FAILURES} -eq 0 ]]; then
  echo "All tests passed."
  exit 0
else
  echo "${FAILURES} test(s) failed."
  exit 1
fi
