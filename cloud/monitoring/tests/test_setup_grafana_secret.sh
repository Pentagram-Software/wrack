#!/bin/bash
# Shell-level regression tests for cloud/monitoring/setup-grafana-secret.sh
#
# Covers behavior that's hard to unit test in Python: the scratch-file
# lifecycle interacting with pre-existing paths, concurrent invocations, and
# process interruption. Complements write_credentials.py's pytest suite,
# which covers the JSON-assembly logic in isolation.
#
# Run from workspace root:
#   bash cloud/monitoring/tests/test_setup_grafana_secret.sh
#
# Uses a fake `gcloud` (and, for one test, a fake `python3`) on PATH so it
# never touches real GCP resources.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITORING_DIR="$(dirname "${SCRIPT_DIR}")"
SCRIPT="${MONITORING_DIR}/setup-grafana-secret.sh"

FAILURES=0
pass() { echo "  ✓ $*"; }
fail() { echo "  ✗ $*"; FAILURES=$((FAILURES + 1)); }

# Extract the path reserve_key_file() chose, from a captured run's stdout.
extract_key_file() {
  grep -oE 'Writing credentials → .*\.\.\.' "$1" 2>/dev/null \
    | tail -n1 \
    | sed -E 's/.*→ (.*)\.\.\.$/\1/'
}

TEST_TMP_DIR="$(mktemp -d)"
FAKE_BIN_DIR="$(mktemp -d)"

cleanup_all() {
  rm -rf "${TEST_TMP_DIR}" "${FAKE_BIN_DIR}"
}
trap cleanup_all EXIT

# Fake gcloud: enough of the real CLI surface for setup-grafana-secret.sh to
# run its full flow without touching real GCP. "secrets create" optionally
# sleeps (FAKE_GCLOUD_CREATE_DELAY) so tests can interrupt the script while
# a real secret upload would still be in flight, and optionally captures the
# --data-file contents (CAPTURE_FILE) so tests can inspect what was about to
# be uploaded. "secrets describe" mimics real gcloud error text — NOT_FOUND
# by default, or FAKE_GCLOUD_DESCRIBE_ERROR verbatim to simulate a different
# failure (e.g. PERMISSION_DENIED).
cat > "${FAKE_BIN_DIR}/gcloud" <<'FAKE_GCLOUD'
#!/bin/bash
case "$*" in
  "config set project"*) exit 0 ;;
  "auth list"*) echo "fake@example.com"; exit 0 ;;
  "secrets describe"*)
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
    sleep "${FAKE_GCLOUD_CREATE_DELAY:-0}"
    exit 0
    ;;
  "secrets versions describe"*) echo "ENABLED"; exit 0 ;;
  *) echo "unhandled fake gcloud call: $*" >&2; exit 1 ;;
esac
FAKE_GCLOUD
chmod +x "${FAKE_BIN_DIR}/gcloud"

# ── Test 1: refuses to overwrite a pre-existing explicit --key-file ─────────
test_refuses_preexisting_explicit_path() {
  local target="${TEST_TMP_DIR}/existing.json"
  echo '{"untouched": true}' > "${target}"

  local rc=0
  ( set -e
    source "${SCRIPT}" --otlp-endpoint https://example.grafana.net/otlp \
      --instance-id 123 --key-file "${target}" >/dev/null 2>&1
    reserve_key_file
  ) >/dev/null 2>&1
  rc=$?

  if [[ ${rc} -ne 0 ]] && grep -q '"untouched": true' "${target}"; then
    pass "refuses to overwrite a pre-existing --key-file and leaves its content untouched"
  else
    fail "expected reserve_key_file to refuse an existing --key-file without touching it (rc=${rc})"
  fi
}

# ── Test 2: concurrent default runs get distinct paths, no cross-contamination ─
test_concurrent_runs_use_distinct_paths() {
  local out_a="${TEST_TMP_DIR}/run-a.out" out_b="${TEST_TMP_DIR}/run-b.out"
  local cap_a="${TEST_TMP_DIR}/run-a.captured.json" cap_b="${TEST_TMP_DIR}/run-b.captured.json"

  PATH="${FAKE_BIN_DIR}:${PATH}" CAPTURE_FILE="${cap_a}" GRAFANA_TOKEN="token-A" \
    bash "${SCRIPT}" --otlp-endpoint https://a.example/otlp --instance-id AAA \
    > "${out_a}" 2>&1 &
  local pid_a=$!

  PATH="${FAKE_BIN_DIR}:${PATH}" CAPTURE_FILE="${cap_b}" GRAFANA_TOKEN="token-B" \
    bash "${SCRIPT}" --otlp-endpoint https://b.example/otlp --instance-id BBB \
    > "${out_b}" 2>&1 &
  local pid_b=$!

  local rc_a=0 rc_b=0
  wait "${pid_a}" || rc_a=$?
  wait "${pid_b}" || rc_b=$?

  local path_a path_b
  path_a="$(extract_key_file "${out_a}")"
  path_b="$(extract_key_file "${out_b}")"

  if [[ ${rc_a} -eq 0 && ${rc_b} -eq 0 \
        && -n "${path_a}" && -n "${path_b}" && "${path_a}" != "${path_b}" ]] \
     && grep -q '"token": "token-A"' "${cap_a}" \
     && grep -q '"token": "token-B"' "${cap_b}"; then
    pass "concurrent default runs reserve distinct scratch paths and don't cross-contaminate credentials"
  else
    fail "concurrent runs collided or cross-contaminated (path_a=${path_a} path_b=${path_b} rc_a=${rc_a} rc_b=${rc_b})"
  fi
}

# ── Test 3: a write step that fails/is interrupted partway leaves no plaintext ─
test_failed_write_leaves_no_plaintext() {
  local failing_py_dir="$(mktemp -d)"
  cat > "${failing_py_dir}/python3" <<'FAKE_PY'
#!/bin/bash
# Simulates the write step being killed partway through (e.g. by SIGTERM)
# before it could write any content.
echo "simulated interruption during write" >&2
exit 143
FAKE_PY
  chmod +x "${failing_py_dir}/python3"

  local out="${TEST_TMP_DIR}/failed-write.out"
  PATH="${failing_py_dir}:${FAKE_BIN_DIR}:${PATH}" GRAFANA_TOKEN="token-interrupt" \
    bash "${SCRIPT}" --otlp-endpoint https://interrupt.example/otlp --instance-id 999 \
    > "${out}" 2>&1
  local rc=$?

  local key_file
  key_file="$(extract_key_file "${out}")"
  rm -rf "${failing_py_dir}"

  if [[ ${rc} -ne 0 && -n "${key_file}" && ! -f "${key_file}" ]]; then
    pass "a write step that fails/is interrupted partway leaves no plaintext scratch file behind"
  else
    fail "expected the scratch file to be cleaned up after a failed write (rc=${rc}, key_file=${key_file})"
    [[ -n "${key_file}" ]] && rm -f "${key_file}"
  fi
}

# ── Test 4: SIGTERM while the scratch file exists on disk triggers cleanup ────
test_sigterm_cleans_up_scratch_file() {
  local out="${TEST_TMP_DIR}/sigterm.out"

  PATH="${FAKE_BIN_DIR}:${PATH}" FAKE_GCLOUD_CREATE_DELAY=5 GRAFANA_TOKEN="token-sigterm" \
    bash "${SCRIPT}" --otlp-endpoint https://sigterm.example/otlp --instance-id 999 \
    > "${out}" 2>&1 &
  local pid=$!

  local key_file=""
  for _ in $(seq 1 50); do
    key_file="$(extract_key_file "${out}")"
    [[ -n "${key_file}" && -f "${key_file}" ]] && break
    sleep 0.1
  done

  if [[ -z "${key_file}" || ! -f "${key_file}" ]]; then
    fail "sigterm test setup failed: scratch file never appeared before timeout"
    kill -TERM "${pid}" 2>/dev/null
    wait "${pid}" 2>/dev/null
    return
  fi

  kill -TERM "${pid}"
  wait "${pid}" 2>/dev/null
  sleep 0.2 # give the trap a moment to run rm

  if [[ ! -f "${key_file}" ]]; then
    pass "SIGTERM sent while the scratch file exists on disk triggers cleanup (no plaintext left behind)"
  else
    fail "scratch file ${key_file} survived a SIGTERM sent while it existed on disk"
    rm -f "${key_file}"
  fi
}

# ── Test 5: a non-NOT_FOUND describe failure propagates instead of creating ───
test_non_not_found_describe_error_propagates() {
  local out="${TEST_TMP_DIR}/describe-error.out"
  local cap="${TEST_TMP_DIR}/describe-error.captured.json"
  rm -f "${cap}"

  PATH="${FAKE_BIN_DIR}:${PATH}" CAPTURE_FILE="${cap}" GRAFANA_TOKEN="token-permdenied" \
    FAKE_GCLOUD_DESCRIBE_ERROR="ERROR: (gcloud.secrets.describe) PERMISSION_DENIED: caller lacks permission" \
    bash "${SCRIPT}" --otlp-endpoint https://denied.example/otlp --instance-id 999 \
    > "${out}" 2>&1
  local rc=$?

  local key_file
  key_file="$(extract_key_file "${out}")"

  if [[ ${rc} -ne 0 && ! -f "${cap}" ]] \
     && grep -q "PERMISSION_DENIED" "${out}" \
     && ! grep -q "created in Secret Manager" "${out}"; then
    pass "a non-NOT_FOUND describe failure (e.g. PERMISSION_DENIED) propagates instead of attempting create"
  else
    fail "expected a PERMISSION_DENIED describe error to abort without creating a secret (rc=${rc})"
  fi

  [[ -n "${key_file}" ]] && rm -f "${key_file}"
}

# ── Test 6: --dry-run alone still validates required inputs ──────────────────
test_dry_run_still_validates_required_inputs() {
  local out="${TEST_TMP_DIR}/dry-run-no-inputs.out"

  # No GRAFANA_TOKEN, --otlp-endpoint, or --instance-id — only --dry-run.
  # gcloud/python3 are deliberately NOT on PATH here to prove dry-run
  # doesn't need them to reject missing required inputs.
  PATH="/usr/bin:/bin" bash "${SCRIPT}" --dry-run > "${out}" 2>&1
  local rc=$?

  if [[ ${rc} -ne 0 ]] \
     && grep -q "Missing required inputs" "${out}" \
     && ! grep -q "Setup complete!" "${out}"; then
    pass "--dry-run alone (no token/endpoint/instance-id) fails validation instead of reporting success"
  else
    fail "expected --dry-run with no required inputs to fail validation and never print Setup complete! (rc=${rc})"
  fi
}

# ── Test 7: verification works without secretmanager.versions.access ─────────
test_verification_does_not_require_versions_access() {
  # A caller with roles/secretmanager.admin but NOT roles/secretmanager.
  # secretAccessor can call "versions describe" (metadata) but not "versions
  # access" (payload). This stub fails "versions access" loudly, so the test
  # fails if verify() ever falls back to reading the payload.
  local strict_bin_dir="$(mktemp -d)"
  cat > "${strict_bin_dir}/gcloud" <<'STRICT_GCLOUD'
#!/bin/bash
case "$*" in
  "config set project"*) exit 0 ;;
  "auth list"*) echo "fake@example.com"; exit 0 ;;
  "secrets describe"*)
    echo "${FAKE_GCLOUD_DESCRIBE_ERROR:-ERROR: (gcloud.secrets.describe) NOT_FOUND: Secret not found.}" >&2
    exit 1
    ;;
  "secrets create"*) exit 0 ;;
  "secrets versions access"*)
    echo "ERROR: PERMISSION_DENIED: caller lacks secretmanager.versions.access" >&2
    exit 1
    ;;
  "secrets versions describe"*) echo "ENABLED"; exit 0 ;;
  *) echo "unhandled fake gcloud call: $*" >&2; exit 1 ;;
esac
STRICT_GCLOUD
  chmod +x "${strict_bin_dir}/gcloud"

  local out="${TEST_TMP_DIR}/verify-no-access.out"
  PATH="${strict_bin_dir}:${PATH}" GRAFANA_TOKEN="token-verify" \
    bash "${SCRIPT}" --otlp-endpoint https://verify.example/otlp --instance-id 999 \
    > "${out}" 2>&1
  local rc=$?

  local key_file
  key_file="$(extract_key_file "${out}")"
  [[ -n "${key_file}" ]] && rm -f "${key_file}"
  rm -rf "${strict_bin_dir}"

  if [[ ${rc} -eq 0 ]] && grep -q "Setup complete" "${out}"; then
    pass "verification succeeds on roles/secretmanager.admin alone, without secretmanager.versions.access"
  else
    fail "expected verify() to succeed using only versions.get-level access, not versions.access (rc=${rc})"
  fi
}

echo "Running shell-level regression tests for setup-grafana-secret.sh..."
echo ""
test_refuses_preexisting_explicit_path
test_concurrent_runs_use_distinct_paths
test_failed_write_leaves_no_plaintext
test_sigterm_cleans_up_scratch_file
test_non_not_found_describe_error_propagates
test_dry_run_still_validates_required_inputs
test_verification_does_not_require_versions_access
echo ""

if [[ ${FAILURES} -eq 0 ]]; then
  echo "All tests passed."
  exit 0
else
  echo "${FAILURES} test(s) failed."
  exit 1
fi
