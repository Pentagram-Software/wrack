#!/usr/bin/env bash
# Start Raspberry Pi edge session processes for this login/session only
# (not systemd — no reboot persistence).
#
# Starts:
#   1. video-streamer  (edge/video-streamer/streamer.py) — default UDP
#   2. system metrics collector (edge/monitoring/system_metrics_collector.py)
#
# Usage (on the Pi, after make deploy-edge):
#   bash ~/robot/edge/scripts/start-all.sh
#
# Or from a laptop:
#   make start-edge
#
# Optional env:
#   STREAMER_CHOICE=1|2|3   Streamer protocol prompt answer (default: 1 = UDP)
#   PYTHON=python3          Interpreter to use
#   EDGE_ROOT=...           Override edge/ root (tests use this)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

ensure_run_dirs

if [[ ! -f "${STREAMER_DIR}/streamer.py" ]]; then
  echo "Error: streamer not found at ${STREAMER_DIR}/streamer.py" >&2
  echo "  Did make deploy-edge sync edge/ to this host?" >&2
  exit 1
fi

if [[ ! -f "${MONITORING_DIR}/system_metrics_collector.py" ]]; then
  echo "Error: metrics collector not found at ${MONITORING_DIR}/system_metrics_collector.py" >&2
  exit 1
fi

load_env_file

start_streamer() {
  if is_running "${STREAMER_PID_FILE}"; then
    echo "video-streamer already running (pid $(pid_from_file "${STREAMER_PID_FILE}"))"
    return 0
  fi

  echo "Starting video-streamer (choice=${STREAMER_CHOICE})…"
  (
    cd "${STREAMER_DIR}"
    # Feed the interactive protocol prompt once via stdin. Background the
    # Python process itself (not a bash wrapper) so $! is the streamer PID —
    # otherwise stop-all kills only the wrapper and leaves an orphaned
    # streamer.py still holding the UDP port.
    nohup "${PYTHON}" streamer.py >>"${STREAMER_LOG}" 2>&1 <<<"${STREAMER_CHOICE}" &
    echo $! > "${STREAMER_PID_FILE}"
  )
  # Brief settle so a fast crash is visible in status.
  sleep 0.3
  if is_running "${STREAMER_PID_FILE}"; then
    echo "  video-streamer started (pid $(pid_from_file "${STREAMER_PID_FILE}"), log ${STREAMER_LOG})"
  else
    echo "Error: video-streamer exited immediately — see ${STREAMER_LOG}" >&2
    exit 1
  fi
}

start_metrics() {
  if is_running "${METRICS_PID_FILE}"; then
    echo "system-metrics already running (pid $(pid_from_file "${METRICS_PID_FILE}"))"
    return 0
  fi

  echo "Starting system-metrics collector…"
  (
    cd "${MONITORING_DIR}"
    nohup "${PYTHON}" system_metrics_collector.py \
      >>"${METRICS_LOG}" 2>&1 &
    echo $! > "${METRICS_PID_FILE}"
  )
  sleep 0.3
  if is_running "${METRICS_PID_FILE}"; then
    echo "  system-metrics started (pid $(pid_from_file "${METRICS_PID_FILE}"), log ${METRICS_LOG})"
  else
    echo "Error: system-metrics exited immediately — see ${METRICS_LOG}" >&2
    exit 1
  fi
}

start_streamer
start_metrics

echo "All edge session processes started."
echo "  Stop with: bash ${SCRIPT_DIR}/stop-all.sh   (or: make stop-edge)"
