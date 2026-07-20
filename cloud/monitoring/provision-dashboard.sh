#!/bin/bash
# provision-dashboard.sh — Provision the EV3 health Grafana dashboard (PEN-231)
#
# Two subcommands, mirroring setup-grafana-secret.sh's conventions (PEN-189):
# a one-time credential-storage step, and the actual provisioning call.
#
#   store-credentials   Store a dashboards:write-scoped Grafana Cloud Access
#                        Policy token in GCP Secret Manager. The token is
#                        created manually in Grafana Cloud's UI (Security ->
#                        Access Policies) -- same "no self-service API to
#                        bootstrap it" limitation setup-grafana-secret.sh
#                        documents for the OTLP push credential. This is a
#                        *separate* secret/scope from grafana-cloud-push-
#                        credentials, which is scoped only to metrics:write +
#                        logs:write and must never be reused/broadened for
#                        dashboard writes (docs/monitoring/architecture.md).
#
#   provision            Read that secret back and POST the dashboard JSON
#                        (default: dashboards/wrack-ev3-health.json) to
#                        Grafana Cloud's /api/dashboards/db HTTP API via curl.
#
# Usage:
#   GRAFANA_DASHBOARD_TOKEN=<access-policy-token> \
#   bash provision-dashboard.sh store-credentials \
#     --grafana-url https://<stack-slug>.grafana.net \
#     [--secret-name grafana-cloud-dashboard-credentials] [--dry-run]
#
#   GCP_PROJECT_ID=wrack-control bash provision-dashboard.sh provision \
#     [--dashboard-file cloud/monitoring/dashboards/wrack-ev3-health.json] \
#     [--secret-name grafana-cloud-dashboard-credentials] [--dry-run]
#
# The token is deliberately NOT a CLI flag for store-credentials — it must
# come from the GRAFANA_DASHBOARD_TOKEN environment variable so it never
# appears in shell history or `ps` output (mirrors setup-grafana-secret.sh's
# GRAFANA_TOKEN handling).
#
# Prerequisites:
#   gcloud (authenticated, with roles/secretmanager.admin or equivalent)
#   python3
#   curl (provision subcommand only)

set -euo pipefail

# Ensure any scratch credentials/request file can never be created
# world/group-readable, even for the brief window between open() and a
# later chmod.
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_DASHBOARD_FILE="${SCRIPT_DIR}/dashboards/wrack-ev3-health.json"

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-wrack-control}"
SECRET_NAME="grafana-cloud-dashboard-credentials"
DRY_RUN=false

# store-credentials-only inputs
GRAFANA_URL=""
DASHBOARD_TOKEN="${GRAFANA_DASHBOARD_TOKEN:-}"

# provision-only inputs
DASHBOARD_FILE="${DEFAULT_DASHBOARD_FILE}"

# Scratch files — reserved lazily by the subcommand that needs them, cleaned
# up unconditionally on exit/interrupt so no plaintext credential or request
# body is ever left behind (mirrors setup-grafana-secret.sh's KEY_FILE
# lifecycle).
CREDS_FILE=""
CREDS_FILE_CREATED=false
REQUEST_FILE=""
REQUEST_FILE_CREATED=false

usage() {
  sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ── Argument parsing ────────────────────────────────────────────────────────────
if [[ $# -eq 0 ]]; then
  echo "Missing required subcommand (store-credentials|provision)" >&2
  usage
  exit 1
fi

SUBCOMMAND="$1"
shift

case "${SUBCOMMAND}" in
  store-credentials|provision) ;;
  -h|--help) usage; exit 0 ;;
  *)
    echo "Unknown subcommand: ${SUBCOMMAND}" >&2
    usage
    exit 1
    ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --grafana-url)     GRAFANA_URL="$2"; shift ;;
    --secret-name)     SECRET_NAME="$2"; shift ;;
    --dashboard-file)  DASHBOARD_FILE="$2"; shift ;;
    --dry-run)         DRY_RUN=true ;;
    -h|--help)         usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

cleanup() {
  if [[ "${CREDS_FILE_CREATED}" == "true" && -n "${CREDS_FILE}" && -f "${CREDS_FILE}" ]]; then
    rm -f "${CREDS_FILE}"
  fi
  if [[ "${REQUEST_FILE_CREATED}" == "true" && -n "${REQUEST_FILE}" && -f "${REQUEST_FILE}" ]]; then
    rm -f "${REQUEST_FILE}"
  fi
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

# ── Helpers ─────────────────────────────────────────────────────────────────────
run() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] $*"
  else
    "$@"
  fi
}

info()  { echo "  ▸ $*"; }
ok()    { echo "  ✓ $*"; }
warn()  { echo "  ⚠ $*" >&2; }
err()   { echo "  ✗ $*" >&2; }

print_banner() {
  echo ""
  echo "=================================================="
  echo "  Wrack Monitoring — EV3 Dashboard Provisioning (PEN-231)"
  echo "  Subcommand:  ${SUBCOMMAND}"
  echo "=================================================="
  echo "  Project:     ${PROJECT_ID}"
  echo "  Secret name: ${SECRET_NAME}"
  [[ "${SUBCOMMAND}" == "provision" ]] && echo "  Dashboard:   ${DASHBOARD_FILE}"
  [[ "${DRY_RUN}" == "true" ]] && echo "  Mode:        DRY-RUN (no changes)"
  echo "=================================================="
  echo ""
}

check_common_prerequisites() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    info "Dry-run: skipping tool/auth checks (required inputs are still validated)"
    return
  fi

  local missing=()
  command -v gcloud  &>/dev/null || missing+=(gcloud)
  command -v python3 &>/dev/null || missing+=(python3)
  [[ "${SUBCOMMAND}" == "provision" ]] && { command -v curl &>/dev/null || missing+=(curl); }

  if [[ ${#missing[@]} -gt 0 ]]; then
    err "Missing required tools: ${missing[*]}"
    exit 1
  fi

  if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | grep -q .; then
    err "No active gcloud account. Run: gcloud auth login"
    exit 1
  fi
}

# ── store-credentials ────────────────────────────────────────────────────────

reserve_creds_file() {
  CREDS_FILE="$(mktemp "${TMPDIR:-/tmp}/grafana-dashboard-credentials.XXXXXX")"
  if [[ "${CREDS_FILE}" == *XXXXXX* ]]; then
    err "mktemp did not generate a unique filename on this platform (got: ${CREDS_FILE})"
    exit 1
  fi
  chmod 600 "${CREDS_FILE}"
  CREDS_FILE_CREATED=true
}

cmd_store_credentials() {
  local missing_inputs=()
  [[ -z "${GRAFANA_URL}" ]]     && missing_inputs+=(--grafana-url)
  [[ -z "${DASHBOARD_TOKEN}" ]] && missing_inputs+=(GRAFANA_DASHBOARD_TOKEN env var)

  if [[ ${#missing_inputs[@]} -gt 0 ]]; then
    err "Missing required inputs: ${missing_inputs[*]}"
    exit 1
  fi
  ok "Prerequisites satisfied"

  if [[ "${DRY_RUN}" == "true" ]]; then
    info "Writing credentials → <a fresh mktemp file>..."
    echo "[DRY-RUN] Would write JSON with grafana_url, token to a freshly reserved scratch file"
    echo "[DRY-RUN] gcloud secrets create/update ${SECRET_NAME} --data-file=<scratch file> --project=${PROJECT_ID}"
    return
  fi

  reserve_creds_file
  info "Writing credentials → ${CREDS_FILE}..."
  GRAFANA_URL="${GRAFANA_URL}" GRAFANA_DASHBOARD_TOKEN="${DASHBOARD_TOKEN}" \
    python3 "${SCRIPT_DIR}/write_dashboard_credentials.py" "${CREDS_FILE}"
  ok "Credentials written to ${CREDS_FILE} (permissions: 600)"

  info "Storing credentials in Secret Manager as '${SECRET_NAME}'..."
  local describe_output
  local describe_rc=0
  describe_output="$(gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" 2>&1)" || describe_rc=$?

  if [[ ${describe_rc} -eq 0 ]]; then
    gcloud secrets versions add "${SECRET_NAME}" --data-file="${CREDS_FILE}" --project="${PROJECT_ID}"
    ok "New version added to existing secret '${SECRET_NAME}'"
  elif echo "${describe_output}" | grep -q "NOT_FOUND"; then
    gcloud secrets create "${SECRET_NAME}" --data-file="${CREDS_FILE}" \
      --replication-policy="automatic" --project="${PROJECT_ID}"
    ok "Secret '${SECRET_NAME}' created in Secret Manager"
  else
    err "Could not determine whether secret '${SECRET_NAME}' exists (not a NOT_FOUND error):"
    err "${describe_output}"
    exit 1
  fi

  local version_state
  version_state="$(gcloud secrets versions describe latest --secret="${SECRET_NAME}" \
    --project="${PROJECT_ID}" --format="value(state)")"
  if [[ "${version_state}" != "ENABLED" ]]; then
    err "Secret '${SECRET_NAME}' latest version is in unexpected state: ${version_state:-<empty>}"
    exit 1
  fi

  ok "Secret '${SECRET_NAME}' stored in project ${PROJECT_ID} (latest version: ${version_state})"
  echo ""
  echo "Next: grant this function/operator's identity roles/secretmanager.secretAccessor"
  echo "on '${SECRET_NAME}', then run: bash provision-dashboard.sh provision"
}

# ── provision ────────────────────────────────────────────────────────────────

reserve_request_file() {
  REQUEST_FILE="$(mktemp "${TMPDIR:-/tmp}/grafana-dashboard-request.XXXXXX")"
  if [[ "${REQUEST_FILE}" == *XXXXXX* ]]; then
    err "mktemp did not generate a unique filename on this platform (got: ${REQUEST_FILE})"
    exit 1
  fi
  chmod 600 "${REQUEST_FILE}"
  REQUEST_FILE_CREATED=true
}

cmd_provision() {
  if [[ ! -f "${DASHBOARD_FILE}" ]]; then
    err "Dashboard file not found: ${DASHBOARD_FILE}"
    exit 1
  fi
  if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "${DASHBOARD_FILE}" 2>/dev/null; then
    err "Dashboard file is not valid JSON: ${DASHBOARD_FILE}"
    exit 1
  fi
  ok "Dashboard file is valid JSON: ${DASHBOARD_FILE}"

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] Would fetch credentials from Secret Manager secret '${SECRET_NAME}' (project ${PROJECT_ID})"
    echo "[DRY-RUN] Would POST ${DASHBOARD_FILE} to <grafana_url from secret>/api/dashboards/db"
    return
  fi

  reserve_creds_file
  info "Fetching credentials from Secret Manager secret '${SECRET_NAME}' → ${CREDS_FILE}..."
  gcloud secrets versions access latest --secret="${SECRET_NAME}" --project="${PROJECT_ID}" \
    > "${CREDS_FILE}"
  chmod 600 "${CREDS_FILE}"

  local grafana_url token
  grafana_url="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['grafana_url'])" "${CREDS_FILE}")"
  token="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['token'])" "${CREDS_FILE}")"

  reserve_request_file
  python3 "${SCRIPT_DIR}/build_dashboard_request.py" "${DASHBOARD_FILE}" "${REQUEST_FILE}"

  info "POSTing dashboard to ${grafana_url%/}/api/dashboards/db ..."
  local response http_code body
  response="$(curl -sS -w '\n%{http_code}' -X POST "${grafana_url%/}/api/dashboards/db" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    --data-binary "@${REQUEST_FILE}")"
  http_code="$(echo "${response}" | tail -n1)"
  body="$(echo "${response}" | sed '$d')"

  if [[ "${http_code}" == "200" ]]; then
    ok "Dashboard provisioned successfully (HTTP ${http_code})"
    echo "${body}"
  else
    err "Provisioning failed (HTTP ${http_code}):"
    err "${body}"
    exit 1
  fi
}

# ── Main ────────────────────────────────────────────────────────────────────────
main() {
  print_banner
  check_common_prerequisites
  case "${SUBCOMMAND}" in
    store-credentials) cmd_store_credentials ;;
    provision)         cmd_provision ;;
  esac
  cleanup
}

# Guarded so tests/test_provision_dashboard.sh can `source` this file (with
# args after the path) and call individual functions directly, the same way
# tests/test_setup_grafana_secret.sh already does for setup-grafana-secret.sh.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main
fi
