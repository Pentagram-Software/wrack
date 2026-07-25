#!/usr/bin/env bash
# Stop Raspberry Pi edge session processes started by start-all.sh.
#
# Usage (on the Pi):
#   bash ~/robot/edge/scripts/stop-all.sh
#
# Or from a laptop:
#   make stop-edge

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

stop_one() {
  local name="$1"
  local pid_file="$2"

  if [[ ! -f "${pid_file}" ]]; then
    echo "${name}: not running (no pid file)"
    return 0
  fi

  local pid
  pid="$(pid_from_file "${pid_file}")"
  if [[ -z "${pid}" ]]; then
    echo "${name}: empty pid file — removing"
    rm -f "${pid_file}"
    return 0
  fi

  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "${name}: not running (stale pid ${pid}) — removing pid file"
    rm -f "${pid_file}"
    return 0
  fi

  echo "Stopping ${name} (pid ${pid})…"
  kill "${pid}" 2>/dev/null || true

  # Wait briefly for a clean exit; escalate if needed.
  local i
  for i in 1 2 3 4 5; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      rm -f "${pid_file}"
      echo "  ${name} stopped"
      return 0
    fi
    sleep 0.2
  done

  echo "  ${name} still running — sending SIGKILL"
  kill -9 "${pid}" 2>/dev/null || true
  rm -f "${pid_file}"
  echo "  ${name} killed"
}

stop_one "system-metrics" "${METRICS_PID_FILE}"
stop_one "video-streamer" "${STREAMER_PID_FILE}"

echo "All edge session processes stopped."
