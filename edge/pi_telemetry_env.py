"""
Shared Raspberry Pi telemetry environment loader.

Both ``edge/monitoring/system_metrics_collector.py`` and
``edge/video-streamer/streamer.py`` read the same KEY=VALUE file written by
``edge/scripts/write-pi-telemetry-env.sh`` during ``make deploy-edge`` /
GitHub Actions deploy. Path matches the systemd unit's EnvironmentFile:

    edge/monitoring/system-metrics.env

Parsing is assignment-only (no shell execution), matching systemd
``EnvironmentFile=`` and ``edge/scripts/lib.sh``'s ``load_env_file``.
"""

from __future__ import annotations

import os
import re
from typing import Dict, Optional

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Relative to this file's parent (edge/).
DEFAULT_ENV_RELATIVE = os.path.join("monitoring", "system-metrics.env")


def default_env_path() -> str:
    """Return the absolute default path to ``system-metrics.env``."""
    edge_root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(edge_root, DEFAULT_ENV_RELATIVE)


def parse_env_file(path: str) -> Dict[str, str]:
    """Parse a KEY=VALUE env file. Blank lines and ``#`` comments are ignored.

    Values may be optionally single- or double-quoted. Does not execute shell.
    Raises ``FileNotFoundError`` if *path* does not exist; ``ValueError`` if the
    file contains no usable assignments.
    """
    result: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not _KEY_RE.match(key):
                continue
            if (len(value) >= 2) and (
                (value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")
            ):
                value = value[1:-1]
            result[key] = value
    if not result:
        raise ValueError("no KEY=VALUE assignments found in {}".format(path))
    return result


def load_pi_telemetry_env(
    path: Optional[str] = None,
    *,
    overwrite: bool = False,
) -> Optional[str]:
    """Load the Pi telemetry env file into ``os.environ``.

    Parameters
    ----------
    path:
        Explicit file path. Defaults to :func:`default_env_path`, or
        ``PI_TELEMETRY_ENV_FILE`` if that env var is set.
    overwrite:
        When *False* (default), only set keys that are missing or empty in
        ``os.environ`` — so an already-exported ``TELEMETRY_ENDPOINT`` wins.

    Returns
    -------
    str or None
        The path loaded, or ``None`` if the file does not exist.
    """
    resolved = path or os.environ.get("PI_TELEMETRY_ENV_FILE") or default_env_path()
    if not os.path.isfile(resolved):
        return None

    values = parse_env_file(resolved)
    for key, value in values.items():
        if overwrite or not os.environ.get(key):
            os.environ[key] = value
    return resolved


def ensure_telemetry_endpoint(
    path: Optional[str] = None,
) -> str:
    """Ensure ``TELEMETRY_ENDPOINT`` is set, loading the env file if needed.

    Returns the endpoint string. Raises ``ValueError`` with a clear message if
    it is still missing after attempting to load the file.
    """
    if not os.environ.get("TELEMETRY_ENDPOINT"):
        load_pi_telemetry_env(path)

    endpoint = os.environ.get("TELEMETRY_ENDPOINT", "").strip()
    if not endpoint:
        env_path = path or os.environ.get("PI_TELEMETRY_ENV_FILE") or default_env_path()
        raise ValueError(
            "TELEMETRY_ENDPOINT is not set. Deploy writes it to {} via "
            "`make deploy-edge` (requires PI_DEVICE_TOKEN + GCP_PROJECT_ID), "
            "or export TELEMETRY_ENDPOINT / TELEMETRY_DEVICE_TOKEN yourself.".format(
                env_path
            )
        )
    return endpoint
