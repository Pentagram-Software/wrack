#!/usr/bin/env python3
"""
Grafana Cloud OTLP push credentials JSON builder.

Reads OTLP_ENDPOINT, INSTANCE_ID, and TOKEN from the environment — never from
argv or interpolated into a shell-built Python source string — and writes
them as a JSON object to the path given as the sole CLI argument (or to
stdout if no path is given). Keeping this out of an inline `python3 -c "..."`
call means a token/endpoint containing a quote, backslash, or newline can't
corrupt the JSON or break out of a string literal. Designed to be called
from setup-grafana-secret.sh so the credential assembly stays testable.

Usage:
    OTLP_ENDPOINT=... INSTANCE_ID=... TOKEN=... python3 write_credentials.py <output-path>
"""

from __future__ import annotations

import json
import os
import sys

REQUIRED_ENV_VARS = ("OTLP_ENDPOINT", "INSTANCE_ID", "TOKEN")


def build_credentials(env: dict) -> dict:
    """Build the credentials dict from an environment mapping.

    Assumes all of REQUIRED_ENV_VARS are present; callers should validate
    with missing_env_vars() first.
    """
    return {
        "otlp_endpoint": env["OTLP_ENDPOINT"],
        "instance_id": env["INSTANCE_ID"],
        "token": env["TOKEN"],
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
