#!/bin/bash
#
# Deploy EV3 Robot Controller - DEBUG MODE
#
# This script deploys the robot controller to an EV3 brick with full debugging enabled.
# Debug mode features:
#   - __debug__ is True (all debug code blocks execute)
#   - assert statements are active
#   - Full error messages and stack traces
#   - Useful for development and troubleshooting
#
# Usage:
#   ./scripts/deploy_debug.sh <EV3_IP>
#   ./scripts/deploy_debug.sh <EV3_IP> [additional options]
#
# Examples:
#   ./scripts/deploy_debug.sh 192.168.1.100
#   ./scripts/deploy_debug.sh 192.168.1.100 --verbose
#   ./scripts/deploy_debug.sh 192.168.1.100 --dry-run
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
    echo "This deploys the DEBUG version (unoptimized, __debug__=True)"
    exit 1
fi

EV3_HOST="$1"
shift

echo "=========================================="
echo "EV3 Deployment - DEBUG MODE"
echo "=========================================="
echo "Target: $EV3_HOST"
echo "Mode: debug (full debugging)"
echo ""

python3 "$SCRIPT_DIR/deploy_ev3.py" \
    --host "$EV3_HOST" \
    --mode debug \
    "$@"
