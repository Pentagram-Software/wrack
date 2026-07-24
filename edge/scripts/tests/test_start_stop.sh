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
  rm -rf "${FAKE_EDGE}"
}
trap cleanup EXIT

mkdir -p "${FAKE_EDGE}/video-streamer" "${FAKE_EDGE}/monitoring" "${FAKE_EDGE}/scripts"

# Point the scripts under test at the fake tree via EDGE_ROOT; still use the
# real start/stop/lib from the repo (copied only if we need them adjacent —
# EDGE_ROOT override means we run the real scripts with EDGE_ROOT set).

# Stub streamer: consume one stdin line (the protocol choice), then sleep.
cat > "${FAKE_EDGE}/video-streamer/streamer.py" <<'PY'
import sys
import time
sys.stdin.readline()
open("started.marker", "w").write("ok")
while True:
    time.sleep(3600)
PY

# Stub metrics collector: just sleep.
cat > "${FAKE_EDGE}/monitoring/system_metrics_collector.py" <<'PY'
import time
open("started.marker", "w").write("ok")
while True:
    time.sleep(3600)
PY

# Minimal env file so load_env_file succeeds without a warning path.
cat > "${FAKE_EDGE}/monitoring/system-metrics.env" <<'ENV'
TELEMETRY_ENDPOINT=https://example.test/unifiedIngress
TELEMETRY_DEVICE_TOKEN=test-token
ENV

export EDGE_ROOT="${FAKE_EDGE}"

# ── Test 1: start creates pid files and keeps processes alive ───────────────
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

  local spid mpid
  spid="$(tr -d '[:space:]' < "${FAKE_EDGE}/run/video-streamer.pid")"
  mpid="$(tr -d '[:space:]' < "${FAKE_EDGE}/run/system-metrics.pid")"

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

# ── Test 3: stop kills processes and removes pid files ──────────────────────
test_stop_clears_pids() {
  local spid mpid
  spid="$(tr -d '[:space:]' < "${FAKE_EDGE}/run/video-streamer.pid")"
  mpid="$(tr -d '[:space:]' < "${FAKE_EDGE}/run/system-metrics.pid")"

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

  if ! kill -0 "${spid}" 2>/dev/null && ! kill -0 "${mpid}" 2>/dev/null; then
    pass "both processes are dead after stop"
  else
    fail "one or both processes still alive after stop"
    kill -9 "${spid}" "${mpid}" 2>/dev/null || true
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

# ── Test 5: missing env file warns but still starts ─────────────────────────
test_missing_env_warns() {
  bash "${SCRIPTS_DIR}/stop-all.sh" >/dev/null 2>&1 || true
  rm -f "${FAKE_EDGE}/monitoring/system-metrics.env"

  local out
  out="$(bash "${SCRIPTS_DIR}/start-all.sh" 2>&1)" || {
    fail "start without env file exited non-zero: ${out}"
    return
  }
  if echo "${out}" | grep -qi "not found"; then
    pass "start warns when system-metrics.env is missing"
  else
    fail "start did not warn about missing env file: ${out}"
  fi
  bash "${SCRIPTS_DIR}/stop-all.sh" >/dev/null 2>&1 || true
}

echo "Running edge/scripts start/stop tests…"
test_start_creates_pids
test_start_idempotent
test_stop_clears_pids
test_stop_when_idle
test_missing_env_warns

if [[ "${FAILURES}" -eq 0 ]]; then
  echo "All tests passed."
  exit 0
fi
echo "${FAILURES} test(s) failed."
exit 1
