#!/usr/bin/env bash
# Shared helpers for edge/scripts/start-all.sh and stop-all.sh.
# Not meant to be run directly.

set -euo pipefail

# Resolve the edge/ root: this file lives at edge/scripts/lib.sh.
_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# EDGE_ROOT may be overridden by tests (pointing at a fake tree).
EDGE_ROOT="${EDGE_ROOT:-$(cd "${_SCRIPTS_DIR}/.." && pwd)}"

STREAMER_DIR="${EDGE_ROOT}/video-streamer"
MONITORING_DIR="${EDGE_ROOT}/monitoring"
RUN_DIR="${EDGE_ROOT}/run"
LOG_DIR="${RUN_DIR}/logs"

STREAMER_PID_FILE="${RUN_DIR}/video-streamer.pid"
METRICS_PID_FILE="${RUN_DIR}/system-metrics.pid"
STREAMER_LOG="${LOG_DIR}/video-streamer.log"
METRICS_LOG="${LOG_DIR}/system-metrics.log"

ENV_FILE="${MONITORING_DIR}/system-metrics.env"

# Streamer __main__ still prompts interactively for protocol (1=UDP, 2=TCP,
# 3=HTTP). Session starts default to UDP; override with STREAMER_CHOICE=2|3.
STREAMER_CHOICE="${STREAMER_CHOICE:-1}"

PYTHON="${PYTHON:-python3}"

ensure_run_dirs() {
  mkdir -p "${RUN_DIR}" "${LOG_DIR}"
}

is_running() {
  local pid_file="$1"
  if [[ ! -f "${pid_file}" ]]; then
    return 1
  fi
  local pid
  pid="$(tr -d '[:space:]' < "${pid_file}")"
  if [[ -z "${pid}" ]]; then
    return 1
  fi
  if kill -0 "${pid}" 2>/dev/null; then
    return 0
  fi
  return 1
}

pid_from_file() {
  tr -d '[:space:]' < "$1"
}

load_env_file() {
  if [[ -f "${ENV_FILE}" ]]; then
    # Export every assignment in the env file into this process (and children).
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
    echo "Loaded env from ${ENV_FILE}"
  else
    echo "Warning: ${ENV_FILE} not found — metrics collector will start without TELEMETRY_* vars (sends will fail until the file exists)." >&2
  fi
}
