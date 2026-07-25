#!/usr/bin/env bash
# Shell regression tests for edge/scripts/start-all.sh and stop-all.sh.
#
# Builds a fake edge/ tree with stub Python entry points so the scripts can
# be exercised without Raspberry Pi hardware or the real streamer/collector.
#
# Run from workspace root:
#   bash edge/scripts/tests/test_start_stop.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

FAILURES=0
pass() { echo "  ✓ $*"; }
fail() { echo "  ✗ $*"; FAILURES=$((FAILURES + 1)); }

FAKE_EDGE="$(mktemp -d)"
cleanup() {
  # Best-effort stop against the fake tree before deleting it.
  EDGE_ROOT="${FAKE_EDGE}" bash "${SCRIPTS_DIR}/stop-all.sh" >/dev/null 2>&1 || true
  # Also kill any orphaned stub processes that wrote a pid.marker (in case
  # stop-all fails to track them — the assertion under test).
  for marker in \
    "${FAKE_EDGE}/video-streamer/pid.marker" \
    "${FAKE_EDGE}/monitoring/pid.marker"; do
    if [[ -f "${marker}" ]]; then
      kill -9 "$(tr -d '[:space:]' < "${marker}")" 2>/dev/null || true
    fi
  done
  rm -rf "${FAKE_EDGE}"
}
trap cleanup EXIT

mkdir -p "${FAKE_EDGE}/video-streamer" "${FAKE_EDGE}/monitoring" "${FAKE_EDGE}/scripts"

# Point the scripts under test at the fake tree via EDGE_ROOT; still use the
# real start/stop/lib from the repo (EDGE_ROOT override).

# Stub streamer: consume one stdin line (the protocol choice), write its own
# PID to pid.marker, then sleep. The pid.marker is what catches a stop that
# only kills a bash wrapper while leaving Python orphaned.
cat > "${FAKE_EDGE}/video-streamer/streamer.py" <<'PY'
import os
import sys
import time
sys.stdin.readline()
open("pid.marker", "w").write(str(os.getpid()))
while True:
    time.sleep(3600)
PY

# Stub metrics collector: write its own PID, then sleep.
cat > "${FAKE_EDGE}/monitoring/system_metrics_collector.py" <<'PY'
import os
import time
open("pid.marker", "w").write(str(os.getpid()))
while True:
    time.sleep(3600)
PY

# Minimal env file so load_env_file succeeds without a warning path.
cat > "${FAKE_EDGE}/monitoring/system-metrics.env" <<'ENV'
TELEMETRY_ENDPOINT=https://example.test/unifiedIngress
TELEMETRY_DEVICE_TOKEN=test-token
ENV

export EDGE_ROOT="${FAKE_EDGE}"

wait_for_marker() {
  local marker="$1"
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if [[ -f "${marker}" ]]; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

# ── Test 1: start creates pid files that match the real Python PIDs ─────────
test_start_creates_pids() {
  local out
  out="$(bash "${SCRIPTS_DIR}/start-all.sh" 2>&1)" || {
    fail "start-all.sh exited non-zero: ${out}"
    return
  }

  if [[ -f "${FAKE_EDGE}/run/video-streamer.pid" ]] && \
     [[ -f "${FAKE_EDGE}/run/system-metrics.pid" ]]; then
    pass "start-all writes both pid files"
  else
    fail "start-all missing pid files (out=${out})"
    return
  fi

  if ! wait_for_marker "${FAKE_EDGE}/video-streamer/pid.marker" || \
     ! wait_for_marker "${FAKE_EDGE}/monitoring/pid.marker"; then
    fail "stubs did not write pid.marker in time"
    return
  fi

  local spid mpid smarker mmarker
  spid="$(tr -d '[:space:]' < "${FAKE_EDGE}/run/video-streamer.pid")"
  mpid="$(tr -d '[:space:]' < "${FAKE_EDGE}/run/system-metrics.pid")"
  smarker="$(tr -d '[:space:]' < "${FAKE_EDGE}/video-streamer/pid.marker")"
  mmarker="$(tr -d '[:space:]' < "${FAKE_EDGE}/monitoring/pid.marker")"

  if [[ "${spid}" == "${smarker}" ]] && [[ "${mpid}" == "${mmarker}" ]]; then
    pass "pid files match real Python process PIDs (not a wrapper)"
  else
    fail "pid-file/Python mismatch: streamer file=${spid} marker=${smarker}; metrics file=${mpid} marker=${mmarker}"
  fi

  if kill -0 "${spid}" 2>/dev/null && kill -0 "${mpid}" 2>/dev/null; then
    pass "both processes are alive after start"
  else
    fail "one or both processes died immediately (streamer=${spid} metrics=${mpid})"
    echo "---- streamer log ----"
    cat "${FAKE_EDGE}/run/logs/video-streamer.log" 2>/dev/null || true
    echo "---- metrics log ----"
    cat "${FAKE_EDGE}/run/logs/system-metrics.log" 2>/dev/null || true
  fi
}

# ── Test 2: second start is idempotent (already running) ────────────────────
test_start_idempotent() {
  local out
  out="$(bash "${SCRIPTS_DIR}/start-all.sh" 2>&1)" || {
    fail "second start-all exited non-zero: ${out}"
    return
  }
  if echo "${out}" | grep -q "already running"; then
    pass "second start reports already running"
  else
    fail "second start did not say already running: ${out}"
  fi
}

# ── Test 3: stop kills the real Python PIDs (not just wrappers) ──────────────
test_stop_clears_pids() {
  local spid mpid smarker mmarker
  spid="$(tr -d '[:space:]' < "${FAKE_EDGE}/run/video-streamer.pid")"
  mpid="$(tr -d '[:space:]' < "${FAKE_EDGE}/run/system-metrics.pid")"
  smarker="$(tr -d '[:space:]' < "${FAKE_EDGE}/video-streamer/pid.marker")"
  mmarker="$(tr -d '[:space:]' < "${FAKE_EDGE}/monitoring/pid.marker")"

  local out
  out="$(bash "${SCRIPTS_DIR}/stop-all.sh" 2>&1)" || {
    fail "stop-all.sh exited non-zero: ${out}"
    return
  }

  if [[ ! -f "${FAKE_EDGE}/run/video-streamer.pid" ]] && \
     [[ ! -f "${FAKE_EDGE}/run/system-metrics.pid" ]]; then
    pass "stop-all removes both pid files"
  else
    fail "stop-all left pid files behind"
  fi

  # Assert against the marker PIDs (the real Python processes), not only the
  # pid-file values — a buggy stop that kills a wrapper but leaves Python
  # orphaned would otherwise stay green.
  if ! kill -0 "${smarker}" 2>/dev/null && ! kill -0 "${mmarker}" 2>/dev/null; then
    pass "both real Python processes are dead after stop"
  else
    fail "one or both Python processes still alive after stop (streamer=${smarker} metrics=${mmarker})"
    kill -9 "${smarker}" "${mmarker}" "${spid}" "${mpid}" 2>/dev/null || true
  fi
}

# ── Test 4: stop is safe when nothing is running ────────────────────────────
test_stop_when_idle() {
  local out rc=0
  out="$(bash "${SCRIPTS_DIR}/stop-all.sh" 2>&1)" || rc=$?
  if [[ "${rc}" -eq 0 ]]; then
    pass "stop-all is a no-op when nothing is running"
  else
    fail "stop-all failed when idle (rc=${rc}): ${out}"
  fi
}

# ── Test 5: missing env file / TELEMETRY_ENDPOINT fails start ───────────────
test_missing_env_fails() {
  bash "${SCRIPTS_DIR}/stop-all.sh" >/dev/null 2>&1 || true
  rm -f "${FAKE_EDGE}/monitoring/system-metrics.env"

  local out rc=0
  out="$(
    env -u TELEMETRY_ENDPOINT -u TELEMETRY_DEVICE_TOKEN \
      bash "${SCRIPTS_DIR}/start-all.sh" 2>&1
  )" || rc=$?
  if [[ "${rc}" -ne 0 ]] && echo "${out}" | grep -qi "TELEMETRY_ENDPOINT"; then
    pass "start fails clearly when system-metrics.env / TELEMETRY_ENDPOINT is missing"
  else
    fail "expected start to fail mentioning TELEMETRY_ENDPOINT (rc=${rc}): ${out}"
  fi
}

# ── Test 6: env file is KEY=VALUE-only (no shell execution) ─────────────────
test_env_file_no_shell_exec() {
  bash "${SCRIPTS_DIR}/stop-all.sh" >/dev/null 2>&1 || true
  local marker="${FAKE_EDGE}/pwned.marker"
  rm -f "${marker}"

  # If load_env_file still used `source`, this would create pwned.marker.
  cat > "${FAKE_EDGE}/monitoring/system-metrics.env" <<ENV
TELEMETRY_ENDPOINT=https://example.test/unifiedIngress
TELEMETRY_DEVICE_TOKEN=test-token
EVIL=\$(touch ${marker})
ENV

  local out
  out="$(bash "${SCRIPTS_DIR}/start-all.sh" 2>&1)" || {
    fail "start with shell-looking env exited non-zero: ${out}"
    return
  }

  if [[ ! -f "${marker}" ]]; then
    pass "env loader does not execute shell in values (systemd EnvironmentFile semantics)"
  else
    fail "env loader executed shell in system-metrics.env (pwned.marker was created)"
  fi
  bash "${SCRIPTS_DIR}/stop-all.sh" >/dev/null 2>&1 || true
}

echo "Running edge/scripts start/stop tests…"
test_start_creates_pids
test_start_idempotent
test_stop_clears_pids
test_stop_when_idle
test_missing_env_fails
test_env_file_no_shell_exec

if [[ "${FAILURES}" -eq 0 ]]; then
  echo "All tests passed."
  exit 0
fi
echo "${FAILURES} test(s) failed."
exit 1
