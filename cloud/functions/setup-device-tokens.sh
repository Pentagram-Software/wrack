#!/bin/bash
# setup-device-tokens.sh — Generate and store per-device ingress tokens in GCP Secret Manager
# PEN-227: Implement unified ingress Cloud Function: per-device auth + type-field routing
#
# Generates a random token per device_id and stores them as one JSON map secret
# (device-tokens) in GCP Secret Manager, following the same storage pattern as
# telemetry-writer-key and grafana-cloud-push-credentials (see
# docs/data-tracking/setup-iam.md). The unified ingress Cloud Function
# (ingress.js) reads this secret at cold start to validate the X-Device-Id +
# X-Device-Token headers each request presents.
#
# Existing tokens for devices not named on the command line are preserved —
# this script merges into the secret, it never clobbers the whole map. Use
# --rotate to force-regenerate a token for a device that already has one.
#
# Usage:
#   GCP_PROJECT_ID=wrack-control bash setup-device-tokens.sh \
#     --device-id ev3-001 \
#     --device-id rpi-camera-01 \
#     [options]
#
# Options:
#   --rotate DEVICE_ID   Force-regenerate the token for this device even if one already exists
#                         (repeatable)
#   --secret-name NAME   Secret Manager secret name (default: device-tokens)
#   --key-file PATH      Local scratch file for the JSON payload (default: ./device-tokens.json)
#   --dry-run            Print every command without executing it
#
# Prerequisites:
#   gcloud (authenticated, with roles/secretmanager.admin or equivalent)
#   python3

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-wrack-control}"

DEVICE_IDS=()
ROTATE_IDS=()

# Set by write_credentials_file() to the secret's latest version identifier
# at the moment it was read (or "<none>" if the secret didn't exist yet).
# store_in_secret_manager() re-checks this right before writing — an
# optimistic-concurrency guard against two concurrent runs each reading the
# same version and the second write silently discarding the first run's
# changes (e.g. un-rotating a token someone else just rotated).
BASE_VERSION=""

# Defaults — overridable via flags
SECRET_NAME="device-tokens"
KEY_FILE="./device-tokens.json"
DRY_RUN=false

# ── Argument parsing ────────────────────────────────────────────────────────────
usage() {
  sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device-id)    DEVICE_IDS+=("$2"); shift ;;
    --rotate)       ROTATE_IDS+=("$2"); shift ;;
    --secret-name)  SECRET_NAME="$2"; shift ;;
    --key-file)     KEY_FILE="$2"; shift ;;
    --dry-run)      DRY_RUN=true ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

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

# Prints the secret's current latest enabled version resource name, or
# "<none>" if the secret doesn't exist. Used for the optimistic-concurrency
# check between write_credentials_file() and store_in_secret_manager().
latest_secret_version() {
  if ! gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "<none>"
    return
  fi
  gcloud secrets versions list "${SECRET_NAME}" \
    --project="${PROJECT_ID}" \
    --filter='state=enabled' \
    --sort-by='~createTime' \
    --limit=1 \
    --format='value(name)'
}

print_banner() {
  echo ""
  echo "=================================================="
  echo "  Wrack Ingress — Device Token Setup (PEN-227)"
  echo "=================================================="
  echo "  Project:     ${PROJECT_ID}"
  echo "  Secret name: ${SECRET_NAME}"
  echo "  Key file:    ${KEY_FILE}"
  echo "  Devices:     ${DEVICE_IDS[*]:-<none>}"
  [[ ${#ROTATE_IDS[@]} -gt 0 ]] && echo "  Rotating:    ${ROTATE_IDS[*]}"
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

  if [[ ${#DEVICE_IDS[@]} -eq 0 && ${#ROTATE_IDS[@]} -eq 0 ]]; then
    err "No devices specified. Pass at least one --device-id or --rotate."
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

# ── Step 2: Fetch existing tokens (if any) and merge in new/rotated ones ───────
write_credentials_file() {
  info "Building device-token map → ${KEY_FILE}..."

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] Would fetch existing secret '${SECRET_NAME}' (if present), merge in tokens for: ${DEVICE_IDS[*]:-<none>}, rotate: ${ROTATE_IDS[*]:-<none>}, write to ${KEY_FILE}"
    return
  fi

  # A `trap ... RETURN` set here does NOT reliably fire when this function
  # itself returns — in practice it fires on the *next* function return in
  # the call chain (main()'s, once every step here has already finished),
  # by which point existing_file is out of scope and `set -u` kills the
  # script with "unbound variable" after the secret was already stored
  # successfully. Cleaned up explicitly at the end of this function instead.
  local existing_file
  existing_file="$(mktemp)"

  BASE_VERSION="$(latest_secret_version)"

  if [[ "${BASE_VERSION}" != "<none>" ]]; then
    gcloud secrets versions access latest --secret="${SECRET_NAME}" --project="${PROJECT_ID}" > "${existing_file}"
    ok "Loaded existing token map (preserving tokens for devices not named on this run)"
  else
    echo '{}' > "${existing_file}"
    info "No existing '${SECRET_NAME}' secret — starting a fresh token map"
  fi

  # Device IDs are passed as one arg per line via stdin, and both file paths
  # via environment variables — never interpolated into the Python source
  # text. --key-file is a user-controlled path; a value containing a quote
  # (or other Python-syntax character) interpolated directly into the
  # source string could break out of the string literal and inject code.
  {
    printf '%s\n' "${DEVICE_IDS[@]:-}"
    echo '---'
    printf '%s\n' "${ROTATE_IDS[@]:-}"
  } | EXISTING_FILE="${existing_file}" OUT_FILE="${KEY_FILE}" python3 -c "
import json, os, secrets, sys

lines = [l.rstrip('\n') for l in sys.stdin]
sep = lines.index('---')
device_ids = [d for d in lines[:sep] if d]
rotate_ids = [d for d in lines[sep + 1:] if d]

existing = json.load(open(os.environ['EXISTING_FILE']))

for device_id in device_ids:
    if device_id not in existing:
        existing[device_id] = secrets.token_hex(32)
        print(f'  ▸ generated new token for {device_id}', file=sys.stderr)
    else:
        print(f'  ▸ {device_id} already has a token, leaving as-is (use --rotate to force)', file=sys.stderr)

for device_id in rotate_ids:
    existing[device_id] = secrets.token_hex(32)
    print(f'  ▸ rotated token for {device_id}', file=sys.stderr)

json.dump(existing, open(os.environ['OUT_FILE'], 'w'), indent=2, sort_keys=True)
"

  rm -f "${existing_file}"
  chmod 600 "${KEY_FILE}"
  ok "Device-token map written to ${KEY_FILE} (permissions: 600)"
}

# ── Step 3: Store in GCP Secret Manager ─────────────────────────────────────────
store_in_secret_manager() {
  info "Storing device-token map in Secret Manager as '${SECRET_NAME}'..."

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] gcloud secrets create/update ${SECRET_NAME} --data-file=${KEY_FILE}"
    return
  fi

  # Optimistic-concurrency check: if the secret changed since we read it (a
  # concurrent run added a version, or created the secret from scratch), our
  # in-memory merge is based on stale data — writing it now would silently
  # discard whatever that other run just changed (e.g. un-rotate a token).
  local current_version
  current_version="$(latest_secret_version)"
  if [[ "${current_version}" != "${BASE_VERSION}" ]]; then
    err "device-tokens secret changed since it was read (was '${BASE_VERSION}', now '${current_version}') —"
    err "another setup-device-tokens.sh run modified it concurrently. Re-run this script to"
    err "merge against the latest state instead of overwriting those changes."
    exit 1
  fi

  if [[ "${current_version}" != "<none>" ]]; then
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
  echo "Tokens for the devices touched this run (copy each into that device's"
  echo "own config now — this is the only time this script prints them):"
  echo ""
  if [[ "${DRY_RUN}" != "true" ]]; then
    printf '%s\n' "${DEVICE_IDS[@]:-}" "${ROTATE_IDS[@]:-}" | OUT_FILE="${KEY_FILE}" python3 -c "
import json, os, sys
touched = sorted({l.rstrip('\n') for l in sys.stdin if l.strip()})
data = json.load(open(os.environ['OUT_FILE']))
for device_id in touched:
    if device_id in data:
        print(f'  {device_id}: {data[device_id]}')
"
  fi
  echo ""
  echo "IMPORTANT — delete the local scratch file now that it's in Secret Manager:"
  echo "    rm ${KEY_FILE}"
  echo ""
  echo "The unified ingress Cloud Function reads this secret at cold start via"
  echo "DEVICE_TOKENS_SECRET. The production deploy workflow"
  echo "(.github/workflows/deploy-cloud-functions.yml) grants read access to"
  echo "unifiedIngress's runtime service account automatically on every deploy —"
  echo "no manual step needed there. For an ad-hoc deploy via cloudbuild.yaml or"
  echo "the npm scripts instead, grant it yourself:"
  echo ""
  echo "  RUNTIME_SA=\$(gcloud functions describe unifiedIngress --gen2 \\"
  echo "    --region=europe-central2 --project=${PROJECT_ID} \\"
  echo "    --format='value(serviceConfig.serviceAccountEmail)')"
  echo "  gcloud secrets add-iam-policy-binding ${SECRET_NAME} \\"
  echo "    --member=\"serviceAccount:\${RUNTIME_SA}\" \\"
  echo "    --role=\"roles/secretmanager.secretAccessor\" \\"
  echo "    --project=${PROJECT_ID}"
  echo ""
  echo "Set TELEMETRY_DEVICE_TOKEN (EV3: telemetry_config.py, Pi: env var) to the"
  echo "matching token above, alongside the existing TELEMETRY_DEVICE_ID."
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
  print_next_steps
}

main
