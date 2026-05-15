#!/usr/bin/env bats
# Tests for cloud/bigquery/setup-iam.sh
#
# Runs with mocked gcloud and bq CLIs so no real GCP credentials are required.
# Run:
#   bats cloud/bigquery/tests/setup-iam.bats
#
# Or from the repo root:
#   bash cloud/bigquery/tests/run-tests.sh

SCRIPT="$BATS_TEST_DIRNAME/../setup-iam.sh"

# ---------------------------------------------------------------------------
# Helpers — mock gcloud and bq
# ---------------------------------------------------------------------------

# Creates stubs in a temp bin directory and prepends it to PATH.
setup() {
  MOCK_BIN="$(mktemp -d)"
  export PATH="$MOCK_BIN:$PATH"

  # Default stub: always succeeds and prints its arguments
  _write_stub() {
    local name="$1"
    cat > "$MOCK_BIN/$name" << 'EOF'
#!/bin/bash
echo "$0 $*" >> "$MOCK_BIN/calls.log"
exit 0
EOF
    chmod +x "$MOCK_BIN/$name"
  }

  _write_stub gcloud
  _write_stub bq

  export MOCK_BIN
  export GCP_PROJECT_ID="test-project"
  export KEY_OUTPUT_FILE="$BATS_TEST_TMPDIR/test-key.json"
}

teardown() {
  rm -rf "$MOCK_BIN"
}

# Record of CLI invocations
calls_log() {
  cat "$MOCK_BIN/calls.log" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Test: dry-run exits 0 and prints DRY RUN lines instead of executing
# ---------------------------------------------------------------------------
@test "dry-run exits 0 without calling gcloud or bq for mutating commands" {
  run bash "$SCRIPT" --dry-run

  [ "$status" -eq 0 ]
  [[ "$output" == *"[DRY RUN]"* ]]

  # The only real gcloud call allowed in dry-run is `config set project`
  # (printed as dry-run), so the mock log should be minimal or empty of SA/IAM calls
  local log
  log="$(calls_log)"
  # service-accounts create must NOT appear in actual calls
  [[ "$log" != *"service-accounts create"* ]]
  # add-iam-policy-binding must NOT appear in actual calls
  [[ "$log" != *"add-iam-policy-binding"* ]]
  # keys create must NOT appear
  [[ "$log" != *"keys create"* ]]
}

# ---------------------------------------------------------------------------
# Test: --skip-key-generation skips key creation step
# ---------------------------------------------------------------------------
@test "--skip-key-generation suppresses key file creation" {
  # Make bq show (dataset check) succeed and bq add-iam-policy-binding succeed
  # gcloud describe (SA exists check) — simulate SA already exists
  cat > "$MOCK_BIN/gcloud" << 'EOF'
#!/bin/bash
echo "gcloud $*" >> "$MOCK_BIN/calls.log"
if [[ "$*" == *"service-accounts describe"* ]]; then
  echo "email: telemetry-writer@test-project.iam.gserviceaccount.com"
  exit 0
fi
exit 0
EOF
  chmod +x "$MOCK_BIN/gcloud"

  run bash "$SCRIPT" --skip-key-generation

  [ "$status" -eq 0 ]
  # Key file must not exist
  [ ! -f "$KEY_OUTPUT_FILE" ]
  # keys create must not appear in calls log
  [[ "$(calls_log)" != *"keys create"* ]]
}

# ---------------------------------------------------------------------------
# Test: script fails when bq show reports dataset missing
# ---------------------------------------------------------------------------
@test "exits non-zero when dataset does not exist" {
  # bq show returns non-zero to simulate missing dataset
  cat > "$MOCK_BIN/bq" << 'EOF'
#!/bin/bash
echo "bq $*" >> "$MOCK_BIN/calls.log"
if [[ "$*" == *"show"* && "$*" == *"--dataset"* ]]; then
  echo "BigQuery error: Not found: Dataset test-project:wrack_telemetry" >&2
  exit 1
fi
exit 0
EOF
  chmod +x "$MOCK_BIN/bq"

  run bash "$SCRIPT" --skip-key-generation

  [ "$status" -ne 0 ]
  [[ "$output" == *"does not exist"* ]] || [[ "$output" == *"deploy.sh"* ]]
}

# ---------------------------------------------------------------------------
# Test: bq add-iam-policy-binding is called with correct arguments
# ---------------------------------------------------------------------------
@test "grants BigQuery Data Editor at dataset scope only" {
  cat > "$MOCK_BIN/gcloud" << 'EOF'
#!/bin/bash
echo "gcloud $*" >> "$MOCK_BIN/calls.log"
if [[ "$*" == *"service-accounts describe"* ]]; then
  exit 0  # SA already exists
fi
exit 0
EOF
  chmod +x "$MOCK_BIN/gcloud"

  run bash "$SCRIPT" --skip-key-generation

  [ "$status" -eq 0 ]

  local log
  log="$(calls_log)"

  # Must call bq add-iam-policy-binding
  [[ "$log" == *"add-iam-policy-binding"* ]]
  # Must include the correct member
  [[ "$log" == *"telemetry-writer@test-project.iam.gserviceaccount.com"* ]]
  # Must include the correct role
  [[ "$log" == *"roles/bigquery.dataEditor"* ]]
  # Must target the dataset (not the project)
  [[ "$log" == *"test-project:wrack_telemetry"* ]]
  # Must NOT call gcloud projects add-iam-policy-binding (project-level)
  [[ "$log" != *"projects add-iam-policy-binding"* ]]
}

# ---------------------------------------------------------------------------
# Test: key file is refused if it already exists (safety guard)
# ---------------------------------------------------------------------------
@test "refuses to overwrite an existing key file" {
  cat > "$MOCK_BIN/gcloud" << 'EOF'
#!/bin/bash
echo "gcloud $*" >> "$MOCK_BIN/calls.log"
if [[ "$*" == *"service-accounts describe"* ]]; then exit 0; fi
exit 0
EOF
  chmod +x "$MOCK_BIN/gcloud"

  # Pre-create the key file
  echo '{"existing": "key"}' > "$KEY_OUTPUT_FILE"

  run bash "$SCRIPT"

  [ "$status" -ne 0 ]
  [[ "$output" == *"already exists"* ]]
}

# ---------------------------------------------------------------------------
# Test: unknown argument causes non-zero exit and usage message
# ---------------------------------------------------------------------------
@test "unknown flag exits with non-zero and prints usage" {
  run bash "$SCRIPT" --unknown-flag

  [ "$status" -ne 0 ]
  [[ "$output" == *"Usage:"* ]] || [[ "$output" == *"Unknown argument"* ]]
}

# ---------------------------------------------------------------------------
# Test: service account name in email matches expected pattern
# ---------------------------------------------------------------------------
@test "service account email is telemetry-writer@<project>.iam.gserviceaccount.com" {
  local sa_email
  sa_email="telemetry-writer@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

  run bash "$SCRIPT" --dry-run

  [ "$status" -eq 0 ]
  [[ "$output" == *"$sa_email"* ]]
}

# ---------------------------------------------------------------------------
# Test: script declares set -euo pipefail for safety
# ---------------------------------------------------------------------------
@test "script uses set -euo pipefail" {
  grep -q "set -euo pipefail" "$SCRIPT"
}

# ---------------------------------------------------------------------------
# Test: script is executable
# ---------------------------------------------------------------------------
@test "setup-iam.sh is executable" {
  [ -x "$SCRIPT" ]
}
