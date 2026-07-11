#!/bin/bash
# setup-grafana-secret.sh — Store Grafana Cloud OTLP push credentials in GCP Secret Manager
# PEN-189: Set up Grafana Cloud free account
#
# The Access Policy token, OTLP gateway endpoint, and instance ID are
# created/found manually in the Grafana Cloud UI (Security → Access
# Policies, scoped to metrics:write + logs:write — never an account-wide
# API key; the OTLP endpoint URL and instance ID are on the stack's
# "OpenTelemetry" configuration guide) and passed to this script, which
# stores them the same way telemetry-writer-key.json is stored (see
# docs/data-tracking/setup-iam.md). There is no gcloud/Grafana API call
# that generates the token itself.
#
# Per docs/monitoring/architecture.md (PEN-218), this credential is for the
# unified-ingress health-leg push Cloud Function only — it must never be
# distributed to the Raspberry Pi or EV3. The push function speaks OTLP
# (metrics + logs in one client), not Prometheus remote_write + Loki push —
# see the PEN-218 comment thread for why.
#
# Usage:
#   GRAFANA_TOKEN=<access-policy-token> \
#   GCP_PROJECT_ID=wrack-control bash setup-grafana-secret.sh \
#     --otlp-endpoint <OTLP gateway URL, e.g. https://otlp-gateway-prod-xx-xxxx.grafana.net/otlp> \
#     --instance-id <Grafana Cloud stack instance ID> \
#     [options]
#
# The token is deliberately NOT a CLI flag — it must come from the
# GRAFANA_TOKEN environment variable so it never appears in shell history
# or `ps` output. The OTLP endpoint and instance ID aren't secret, so they
# stay as flags.
#
# Options:
#   --secret-name NAME   Secret Manager secret name (default: grafana-cloud-push-credentials)
#   --key-file PATH      Local scratch file for the JSON payload (default: ./grafana-cloud-push-credentials.json)
#   --dry-run            Print every command without executing it
#
# Prerequisites:
#   gcloud (authenticated, with roles/secretmanager.admin or equivalent)
#   python3

set -euo pipefail

# Ensure the scratch credentials file can never be created world/group-readable,
# even for the brief window between open() and the later chmod.
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-wrack-control}"

# Required inputs — no defaults, must come from the Grafana Cloud UI
TOKEN="${GRAFANA_TOKEN:-}"
OTLP_ENDPOINT=""
INSTANCE_ID=""

# Defaults — overridable via flags
SECRET_NAME="grafana-cloud-push-credentials"
KEY_FILE="./grafana-cloud-push-credentials.json"
DRY_RUN=false

# Tracks whether write_credentials_file() actually created KEY_FILE, so the
# EXIT trap knows whether there's plaintext to clean up.
KEY_FILE_CREATED=false

# ── Argument parsing ────────────────────────────────────────────────────────────
usage() {
  sed -n '2,34p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --otlp-endpoint)  OTLP_ENDPOINT="$2"; shift ;;
    --instance-id)    INSTANCE_ID="$2"; shift ;;
    --secret-name)    SECRET_NAME="$2"; shift ;;
    --key-file)       KEY_FILE="$2"; shift ;;
    --dry-run)        DRY_RUN=true ;;
    -h|--help)        usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

# Never leave the plaintext credentials file behind, whether the script
# finishes successfully or exits early on an error.
cleanup() {
  if [[ "${KEY_FILE_CREATED}" == "true" && -f "${KEY_FILE}" ]]; then
    rm -f "${KEY_FILE}"
  fi
}
trap cleanup EXIT

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
  echo "  Wrack Monitoring — Grafana Cloud OTLP Secret Setup (PEN-189)"
  echo "=================================================="
  echo "  Project:     ${PROJECT_ID}"
  echo "  Secret name: ${SECRET_NAME}"
  echo "  Key file:    ${KEY_FILE}"
  [[ "${DRY_RUN}" == "true" ]] && echo "  Mode:        DRY-RUN (no changes)"
  echo "=================================================="
  echo ""
}

# ── Pre-flight checks ───────────────────────────────────────────────────────────
check_prerequisites() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    info "Dry-run: skipping prerequisite validation"
    return
  fi

  local missing=()
  command -v gcloud  &>/dev/null || missing+=(gcloud)
  command -v python3 &>/dev/null || missing+=(python3)

  if [[ ${#missing[@]} -gt 0 ]]; then
    err "Missing required tools: ${missing[*]}"
    err "Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
    exit 1
  fi

  if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | grep -q .; then
    err "No active gcloud account. Run: gcloud auth login"
    exit 1
  fi

  local missing_inputs=()
  [[ -z "${TOKEN}" ]]         && missing_inputs+=(GRAFANA_TOKEN env var)
  [[ -z "${OTLP_ENDPOINT}" ]] && missing_inputs+=(--otlp-endpoint)
  [[ -z "${INSTANCE_ID}" ]]   && missing_inputs+=(--instance-id)

  if [[ ${#missing_inputs[@]} -gt 0 ]]; then
    err "Missing required inputs: ${missing_inputs[*]}"
    err "Get these values from the Grafana Cloud portal's OpenTelemetry configuration guide + a scoped Access Policy token."
    exit 1
  fi

  ok "Prerequisites satisfied"
}

# ── Step 1: Set active project ──────────────────────────────────────────────────
set_project() {
  info "Setting active project to ${PROJECT_ID}..."
  run gcloud config set project "${PROJECT_ID}"
  ok "Project set to ${PROJECT_ID}"
}

# ── Step 2: Assemble the credentials JSON ──────────────────────────────────────
write_credentials_file() {
  info "Writing credentials → ${KEY_FILE}..."

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] Would write JSON with otlp_endpoint, instance_id, token to ${KEY_FILE}"
    return
  fi

  # Values are passed via environment, not interpolated into a Python source
  # string, so a token/endpoint containing a quote or backslash can't corrupt
  # the JSON or break out of a string literal (see write_credentials.py).
  OTLP_ENDPOINT="${OTLP_ENDPOINT}" INSTANCE_ID="${INSTANCE_ID}" TOKEN="${TOKEN}" \
    python3 "${SCRIPT_DIR}/write_credentials.py" "${KEY_FILE}"
  KEY_FILE_CREATED=true

  chmod 600 "${KEY_FILE}"
  ok "Credentials written to ${KEY_FILE} (permissions: 600)"
}

# ── Step 3: Store in GCP Secret Manager ─────────────────────────────────────────
store_in_secret_manager() {
  info "Storing credentials in Secret Manager as '${SECRET_NAME}'..."

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] gcloud secrets create/update ${SECRET_NAME} --data-file=${KEY_FILE}"
    return
  fi

  if gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
    run gcloud secrets versions add "${SECRET_NAME}" \
      --data-file="${KEY_FILE}" \
      --project="${PROJECT_ID}"
    ok "New version added to existing secret '${SECRET_NAME}'"
  else
    run gcloud secrets create "${SECRET_NAME}" \
      --data-file="${KEY_FILE}" \
      --replication-policy="automatic" \
      --project="${PROJECT_ID}"
    ok "Secret '${SECRET_NAME}' created in Secret Manager"
  fi
}

# ── Verification ────────────────────────────────────────────────────────────────
verify() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] Skipping verification"
    return
  fi

  info "Verifying secret is readable..."
  gcloud secrets versions access latest \
    --secret="${SECRET_NAME}" \
    --project="${PROJECT_ID}" \
    > /dev/null

  ok "Secret '${SECRET_NAME}' stored and readable in project ${PROJECT_ID}"
}

# ── Post-run instructions ───────────────────────────────────────────────────────
print_next_steps() {
  echo ""
  echo "=================================================="
  echo "  Setup complete!"
  echo "=================================================="
  echo ""
  if [[ "${DRY_RUN}" != "true" ]]; then
    echo "The local scratch file (${KEY_FILE}) has been deleted automatically —"
    echo "the credentials now live only in Secret Manager."
    echo ""
  fi
  echo "This secret must only ever be read by the unified-ingress health-leg"
  echo "push Cloud Function's service account — never by the Raspberry Pi or"
  echo "EV3, and never committed to the repo. Once that function exists (see"
  echo "PEN-218), grant it read access:"
  echo ""
  echo "  gcloud secrets add-iam-policy-binding ${SECRET_NAME} \\"
  echo "    --member=\"serviceAccount:<HEALTH_LEG_FUNCTION_SA>@${PROJECT_ID}.iam.gserviceaccount.com\" \\"
  echo "    --role=\"roles/secretmanager.secretAccessor\" \\"
  echo "    --project=${PROJECT_ID}"
  echo ""
  echo "The health-leg push function should use an OTLP client against"
  echo "otlp_endpoint, authenticating with Basic Auth (instance_id : token)"
  echo "for both the metrics and logs exporters."
  echo ""
  echo "Related tickets:"
  echo "  PEN-218 — unified ingress architecture (health-leg push function, not yet built)"
  echo "  PEN-207 / PEN-208 — 72h retention config on this Grafana Cloud stack"
  echo ""
}

# ── Main ────────────────────────────────────────────────────────────────────────
main() {
  print_banner
  check_prerequisites
  set_project
  write_credentials_file
  store_in_secret_manager
  verify
  cleanup
  print_next_steps
}

main
