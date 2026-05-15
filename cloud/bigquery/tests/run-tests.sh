#!/bin/bash
# Run all BigQuery infrastructure tests
# Usage: bash cloud/bigquery/tests/run-tests.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v bats &>/dev/null; then
  echo "ERROR: 'bats' not found."
  echo "Install via: npm install -g bats"
  echo "  or: https://bats-core.readthedocs.io/en/stable/installation.html"
  exit 1
fi

echo "Running BigQuery IAM setup tests..."
bats "$SCRIPT_DIR/setup-iam.bats"
