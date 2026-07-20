#!/usr/bin/env python3
"""
Grafana Cloud /api/dashboards/db request-body builder (PEN-231).

Wraps a dashboard definition JSON file (e.g.
cloud/monitoring/dashboards/wrack-ev3-health.json) in the envelope Grafana's
dashboard-provisioning HTTP API expects, and writes it to a file so
provision-dashboard.sh can hand it to curl via --data-binary @<file>
rather than interpolating JSON into a shell command line (same rationale as
write_credentials.py / write_dashboard_credentials.py: avoids quoting/escaping
bugs and keeps the assembly step independently testable).

overwrite=true makes re-running provision-dashboard.sh against an unchanged
uid idempotent -- it updates the existing dashboard rather than erroring on
a duplicate uid.

Usage:
    python3 build_dashboard_request.py <dashboard-json-path> <output-path>
"""

from __future__ import annotations

import json
import sys

REQUEST_MESSAGE = "Provisioned by provision-dashboard.sh (PEN-231)"


def build_request(dashboard: dict) -> dict:
    """Wrap a parsed dashboard dict in the /api/dashboards/db envelope."""
    return {
        "dashboard": dashboard,
        "overwrite": True,
        "message": REQUEST_MESSAGE,
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if len(args) != 2:
        print(
            "Usage: build_dashboard_request.py <dashboard-json-path> <output-path>",
            file=sys.stderr,
        )
        return 1

    dashboard_path, output_path = args

    try:
        with open(dashboard_path) as f:
            dashboard = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not read/parse dashboard JSON at {dashboard_path}: {exc}", file=sys.stderr)
        return 1

    with open(output_path, "w") as f:
        json.dump(build_request(dashboard), f)

    return 0


if __name__ == "__main__":
    sys.exit(main())
