#!/usr/bin/env bash
# Shell tests for edge/scripts/write-pi-telemetry-env.sh
#
# Run from workspace root:
#   bash edge/scripts/tests/test_write_pi_telemetry_env.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WRITE_SCRIPT="${SCRIPTS_DIR}/write-pi-telemetry-env.sh"

FAILURES=0
pass() { echo "  ✓ $*"; }
fail() { echo "  ✗ $*"; FAILURES=$((FAILURES + 1)); }

# ── Test 1: --stdout requires PI_DEVICE_TOKEN ───────────────────────────────
test_requires_device_token() {
  local out rc=0
  out="$(
    env -u PI_DEVICE_TOKEN GCP_PROJECT_ID=wrack-control \
      bash "${WRITE_SCRIPT}" --stdout 2>&1
  )" || rc=$?
  if [[ "${rc}" -ne 0 ]] && echo "${out}" | grep -q "PI_DEVICE_TOKEN"; then
    pass "refuses to write without PI_DEVICE_TOKEN"
  else
    fail "expected failure mentioning PI_DEVICE_TOKEN (rc=${rc}): ${out}"
  fi
}

# ── Test 2: --stdout requires GCP_PROJECT_ID ────────────────────────────────
test_requires_project_id() {
  local out rc=0
  out="$(
    env -u GCP_PROJECT_ID PI_DEVICE_TOKEN=tok \
      bash "${WRITE_SCRIPT}" --stdout 2>&1
  )" || rc=$?
  if [[ "${rc}" -ne 0 ]] && echo "${out}" | grep -q "GCP_PROJECT_ID"; then
    pass "refuses to write without GCP_PROJECT_ID"
  else
    fail "expected failure mentioning GCP_PROJECT_ID (rc=${rc}): ${out}"
  fi
}

# ── Test 3: --stdout emits expected KEY=VALUE content ───────────────────────
test_stdout_contents() {
  local out
  out="$(
    PI_DEVICE_TOKEN='tok-abc' \
    GCP_PROJECT_ID='wrack-control' \
    PI_RPI_DEVICE_ID='rpi-camera-01' \
      bash "${WRITE_SCRIPT}" --stdout
  )" || {
    fail "--stdout exited non-zero"
    return
  }

  if echo "${out}" | grep -qx 'TELEMETRY_ENDPOINT=https://europe-central2-wrack-control.cloudfunctions.net/unifiedIngress' \
     && echo "${out}" | grep -qx 'TELEMETRY_DEVICE_TOKEN=tok-abc' \
     && echo "${out}" | grep -qx 'RPI_DEVICE_ID=rpi-camera-01'; then
    pass "--stdout emits endpoint, token, and device id"
  else
    fail "unexpected --stdout content: ${out}"
  fi
}

# ── Test 4: default device id when PI_RPI_DEVICE_ID unset ───────────────────
test_default_device_id() {
  local out
  out="$(
    env -u PI_RPI_DEVICE_ID \
    PI_DEVICE_TOKEN='tok' GCP_PROJECT_ID='proj' \
      bash "${WRITE_SCRIPT}" --stdout
  )"
  if echo "${out}" | grep -qx 'RPI_DEVICE_ID=rpi-camera-01'; then
    pass "defaults RPI_DEVICE_ID to rpi-camera-01"
  else
    fail "default device id missing: ${out}"
  fi
}

echo "Running write-pi-telemetry-env.sh tests…"
test_requires_device_token
test_requires_project_id
test_stdout_contents
test_default_device_id

if [[ "${FAILURES}" -eq 0 ]]; then
  echo "All tests passed."
  exit 0
fi
echo "${FAILURES} test(s) failed."
exit 1
