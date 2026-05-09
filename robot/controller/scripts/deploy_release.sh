#!/bin/bash
#
# Deploy EV3 Robot Controller - RELEASE MODE
#
# This script deploys the robot controller to an EV3 brick with optimization enabled.
# Release mode benefits:
#   - __debug__ is False (skips debug code blocks)
#   - assert statements are removed
#   - Better performance on resource-constrained EV3
#
# Usage:
#   ./scripts/deploy_release.sh <EV3_IP>
#   ./scripts/deploy_release.sh <EV3_IP> [additional options]
#
# Examples:
#   ./scripts/deploy_release.sh 192.168.1.100
#   ./scripts/deploy_release.sh 192.168.1.100 --verbose
#   ./scripts/deploy_release.sh 192.168.1.100 --dry-run
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROLLER_DIR="$(dirname "$SCRIPT_DIR")"

if [ -z "$1" ]; then
    echo "Usage: $0 <EV3_IP> [additional options]"
    echo ""
    echo "Examples:"
    echo "  $0 192.168.1.100"
    echo "  $0 192.168.1.100 --verbose"
    echo "  $0 192.168.1.100 --dry-run"
    echo ""
    echo "This deploys the RELEASE version (optimized, __debug__=False)"
    exit 1
fi

EV3_HOST="$1"
shift

echo "=========================================="
echo "EV3 Deployment - RELEASE MODE"
echo "=========================================="
echo "Target: $EV3_HOST"
echo "Mode: release (optimized)"
echo ""

python3 "$SCRIPT_DIR/deploy_ev3.py" \
    --host "$EV3_HOST" \
    --mode release \
    "$@"
