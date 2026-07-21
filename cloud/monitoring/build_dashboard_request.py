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

The committed dashboard JSON's panel query is PLACEHOLDER_METRIC_NAME, not a
live value -- PEN-231's code review flagged that shipping an unverified
metric-name guess as the *active* query risks provisioning a dashboard that
loads successfully but permanently shows no data. --metric-name substitutes
the real, human-confirmed value into every matching target expr at
provisioning time; provision-dashboard.sh requires it for any real (non
--dry-run) call, so the placeholder itself is never the one actually sent
to Grafana Cloud.

Usage:
    python3 build_dashboard_request.py <dashboard-json-path> <output-path> [--metric-name NAME]
"""

from __future__ import annotations

import json
import sys

REQUEST_MESSAGE = "Provisioned by provision-dashboard.sh (PEN-231)"

# Kept in sync with cloud/monitoring/dashboards/wrack-ev3-health.json's
# panel target expr -- see docs/monitoring/ev3-health-dashboard.md for why
# this isn't just committed as the live query.
PLACEHOLDER_METRIC_NAME = "__CONFIRM_METRIC_NAME__"


def build_request(dashboard: dict) -> dict:
    """Wrap a parsed dashboard dict in the /api/dashboards/db envelope."""
    return {
        "dashboard": dashboard,
        "overwrite": True,
        "message": REQUEST_MESSAGE,
    }


def substitute_metric_name(dashboard: dict, metric_name: str) -> dict:
    """Replace every occurrence of PLACEHOLDER_METRIC_NAME in panel target
    exprs with *metric_name*.

    Raises ValueError if the placeholder isn't found anywhere -- this is a
    safety net against silent drift (e.g. the dashboard JSON already having
    been hand-edited to a different query) rather than a normal code path.
    """
    found = False
    for panel in dashboard.get("panels", []):
        for target in panel.get("targets", []):
            if target.get("expr") == PLACEHOLDER_METRIC_NAME:
                target["expr"] = metric_name
                found = True

    if not found:
        raise ValueError(
            f"placeholder {PLACEHOLDER_METRIC_NAME!r} not found in any panel target -- "
            "refusing to silently provision an unrelated query"
        )

    return dashboard


def _parse_args(args: list[str]) -> tuple[str, str, str | None] | None:
    """Returns (dashboard_path, output_path, metric_name) or None if args are invalid."""
    metric_name = None
    positional = []

    i = 0
    while i < len(args):
        if args[i] == "--metric-name":
            if i + 1 >= len(args):
                return None
            metric_name = args[i + 1]
            i += 2
        else:
            positional.append(args[i])
            i += 1

    if len(positional) != 2:
        return None

    return positional[0], positional[1], metric_name


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    parsed = _parse_args(args)
    if parsed is None:
        print(
            "Usage: build_dashboard_request.py <dashboard-json-path> <output-path> [--metric-name NAME]",
            file=sys.stderr,
        )
        return 1

    dashboard_path, output_path, metric_name = parsed

    try:
        with open(dashboard_path) as f:
            dashboard = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not read/parse dashboard JSON at {dashboard_path}: {exc}", file=sys.stderr)
        return 1

    if metric_name is not None:
        try:
            dashboard = substitute_metric_name(dashboard, metric_name)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    with open(output_path, "w") as f:
        json.dump(build_request(dashboard), f)

    return 0


if __name__ == "__main__":
    sys.exit(main())
