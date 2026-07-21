#!/usr/bin/env python3
"""
Grafana Cloud dashboard-provisioning credentials JSON builder.

Companion to write_credentials.py (PEN-189's OTLP push credentials), for the
separate Grafana Service Account token PEN-231's provision-dashboard.sh
needs to call Grafana Cloud's /api/dashboards/db HTTP API. This is
deliberately NOT a Cloud Access Policy token -- Grafana Cloud Access
Policies (what write_credentials.py's OTLP credential uses) do not
authorize the Grafana instance HTTP API at all (dashboards, users, data
sources); only a Service Account token, created in the target stack's own
Grafana UI, does. Kept as its own module rather than extending
write_credentials.py: the two credentials are deliberately different
secrets, of different token types, with different scopes (metrics:write +
logs:write vs. dashboard write access) and must never be merged into one,
per docs/monitoring/architecture.md's "Authenticating the ingress -> health-
leg call" precedent of keeping credentials narrowly scoped.

Reads GRAFANA_URL and GRAFANA_DASHBOARD_TOKEN from the environment -- never
from argv or interpolated into a shell-built Python source string -- and
writes them as a JSON object to the path given as the sole CLI argument (or
to stdout if no path is given). Same rationale as write_credentials.py: a
token/URL containing a quote, backslash, or newline can't corrupt the JSON
or break out of a string literal.

Usage:
    GRAFANA_URL=... GRAFANA_DASHBOARD_TOKEN=... python3 write_dashboard_credentials.py <output-path>
"""

from __future__ import annotations

import json
import os
import sys

REQUIRED_ENV_VARS = ("GRAFANA_URL", "GRAFANA_DASHBOARD_TOKEN")


def build_credentials(env: dict) -> dict:
    """Build the credentials dict from an environment mapping.

    Assumes all of REQUIRED_ENV_VARS are present; callers should validate
    with missing_env_vars() first.
    """
    return {
        "grafana_url": env["GRAFANA_URL"],
        "token": env["GRAFANA_DASHBOARD_TOKEN"],
    }


def missing_env_vars(env: dict) -> list[str]:
    """Return the subset of REQUIRED_ENV_VARS that are unset or empty in env."""
    return [name for name in REQUIRED_ENV_VARS if not env.get(name)]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    missing = missing_env_vars(os.environ)
    if missing:
        print(
            f"ERROR: missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    payload = json.dumps(build_credentials(os.environ), indent=2)

    if args:
        with open(args[0], "w") as f:
            f.write(payload)
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    sys.exit(main())
