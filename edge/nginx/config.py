"""Nginx HLS serving configuration.

Provides :class:`NginxConfigParams` — a validated dataclass that holds every
tunable for the Nginx reverse-proxy that sits in front of the LL-HLS Python
server (``edge/video-streamer/hls/server.py``).

Typical usage
-------------
::

    from config import NginxConfigParams, load_from_env
    import generate_config

    params = load_from_env()          # reads NGINX_* env vars with sensible defaults
    params.validate()                 # raises ValueError on bad values
    conf = generate_config.render(params)
    print(conf)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Nginx MIME-type alias used for M3U8 playlists.
MIME_M3U8 = "application/vnd.apple.mpegurl"

#: Nginx MIME-type alias used for MPEG-TS segment files.
MIME_TS = "video/mp2t"

#: Default upstream host for the Python LL-HLS server.
DEFAULT_UPSTREAM_HOST = "127.0.0.1"

#: Default upstream port for the Python LL-HLS server (matches LLHLSServer default).
DEFAULT_UPSTREAM_PORT = 8888

#: Default port Nginx listens on.
DEFAULT_LISTEN_PORT = 80

#: Immutable segments should be cached for a very long time (1 year in seconds).
DEFAULT_SEGMENT_CACHE_MAX_AGE = 31_536_000

#: Proxy read-timeout for playlist requests (must exceed the LL-HLS blocking-
#: reload server-side timeout of 10 s; we set 15 s to give comfortable margin).
DEFAULT_PLAYLIST_PROXY_TIMEOUT = 15

#: Default ``Access-Control-Allow-Origin`` header value.
DEFAULT_CORS_ORIGIN = "*"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class NginxConfigParams:
    """Parameters that control Nginx HLS serving behaviour.

    All attributes have sane defaults and can be overridden via environment
    variables using :func:`load_from_env`.

    Attributes
    ----------
    upstream_host:
        Hostname or IP of the Python LL-HLS HTTP server.
    upstream_port:
        TCP port of the Python LL-HLS HTTP server.
    listen_port:
        Port on which Nginx will accept incoming HTTP connections.
    segment_cache_max_age:
        ``Cache-Control: max-age`` value (seconds) applied to ``.ts`` segment
        responses.  Segments are immutable once written, so a long TTL is safe.
    playlist_proxy_timeout:
        ``proxy_read_timeout`` value (seconds) for ``.m3u8`` playlist requests.
        Must exceed the server-side blocking-reload timeout (default 10 s).
    cors_origin:
        Value of the ``Access-Control-Allow-Origin`` response header.
    worker_processes:
        Nginx ``worker_processes`` directive.  ``"auto"`` lets Nginx choose.
    worker_connections:
        Nginx ``worker_connections`` directive.
    keepalive_upstream:
        Number of persistent keep-alive connections to the upstream server.
    """

    upstream_host: str = DEFAULT_UPSTREAM_HOST
    upstream_port: int = DEFAULT_UPSTREAM_PORT
    listen_port: int = DEFAULT_LISTEN_PORT
    segment_cache_max_age: int = DEFAULT_SEGMENT_CACHE_MAX_AGE
    playlist_proxy_timeout: int = DEFAULT_PLAYLIST_PROXY_TIMEOUT
    cors_origin: str = DEFAULT_CORS_ORIGIN
    worker_processes: str = "auto"
    worker_connections: int = 1024
    keepalive_upstream: int = 32

    def validate(self) -> None:
        """Raise :class:`ValueError` if any parameter is outside its valid range.

        Checks performed:

        * ``upstream_port`` and ``listen_port``: 1 – 65535
        * ``upstream_port != listen_port`` when ``upstream_host`` is a loopback
          address (avoids an accidental proxy loop)
        * ``segment_cache_max_age`` ≥ 0
        * ``playlist_proxy_timeout`` ≥ 1 (must allow at least 1 s of blocking)
        * ``worker_connections`` ≥ 1
        * ``keepalive_upstream`` ≥ 1
        * ``worker_processes`` is either ``"auto"`` or a positive integer string
        * ``cors_origin`` is non-empty
        """
        errors: List[str] = []

        # Port range checks
        for attr, value in (("upstream_port", self.upstream_port), ("listen_port", self.listen_port)):
            if not isinstance(value, int) or not (1 <= value <= 65535):
                errors.append(f"{attr} must be an integer between 1 and 65535, got {value!r}")

        # Proxy-loop guard: if upstream is on localhost, the ports must differ
        _loopback = {"127.0.0.1", "::1", "localhost"}
        if (
            self.upstream_host in _loopback
            and isinstance(self.upstream_port, int)
            and isinstance(self.listen_port, int)
            and self.upstream_port == self.listen_port
        ):
            errors.append(
                f"upstream_port ({self.upstream_port}) and listen_port ({self.listen_port}) "
                "must differ when upstream_host is a loopback address to avoid a proxy loop"
            )

        # Cache max-age
        if not isinstance(self.segment_cache_max_age, int) or self.segment_cache_max_age < 0:
            errors.append(
                f"segment_cache_max_age must be a non-negative integer, got {self.segment_cache_max_age!r}"
            )

        # Playlist proxy timeout must allow blocking-reload to complete
        if not isinstance(self.playlist_proxy_timeout, int) or self.playlist_proxy_timeout < 1:
            errors.append(
                f"playlist_proxy_timeout must be an integer ≥ 1, got {self.playlist_proxy_timeout!r}"
            )

        # Worker connections
        if not isinstance(self.worker_connections, int) or self.worker_connections < 1:
            errors.append(
                f"worker_connections must be a positive integer, got {self.worker_connections!r}"
            )

        # Keepalive upstream connections
        if not isinstance(self.keepalive_upstream, int) or self.keepalive_upstream < 1:
            errors.append(
                f"keepalive_upstream must be a positive integer, got {self.keepalive_upstream!r}"
            )

        # Worker processes: "auto" or a positive integer string
        if self.worker_processes != "auto":
            try:
                n = int(self.worker_processes)
                if n < 1:
                    raise ValueError()
            except (ValueError, TypeError):
                errors.append(
                    f"worker_processes must be 'auto' or a positive integer string, "
                    f"got {self.worker_processes!r}"
                )

        # CORS origin must not be empty
        if not self.cors_origin or not self.cors_origin.strip():
            errors.append("cors_origin must be a non-empty string")

        if errors:
            raise ValueError("Invalid NginxConfigParams:\n" + "\n".join(f"  - {e}" for e in errors))


# ---------------------------------------------------------------------------
# Environment-variable loader
# ---------------------------------------------------------------------------


def load_from_env() -> NginxConfigParams:
    """Create :class:`NginxConfigParams` from environment variables.

    Environment variables (all optional; defaults are used when absent):

    ============================  =======  =============================
    Variable                      Type     Description
    ============================  =======  =============================
    ``NGINX_UPSTREAM_HOST``       str      LL-HLS Python server host
    ``NGINX_UPSTREAM_PORT``       int      LL-HLS Python server port
    ``NGINX_LISTEN_PORT``         int      Nginx listen port
    ``NGINX_SEGMENT_CACHE_AGE``   int      ``.ts`` cache max-age (s)
    ``NGINX_PLAYLIST_TIMEOUT``    int      Playlist proxy read-timeout (s)
    ``NGINX_CORS_ORIGIN``         str      Access-Control-Allow-Origin
    ``NGINX_WORKER_PROCESSES``    str      ``auto`` or positive integer
    ``NGINX_WORKER_CONNECTIONS``  int      Connections per worker
    ``NGINX_KEEPALIVE_UPSTREAM``  int      Upstream keepalive connections
    ============================  =======  =============================
    """

    def _int(name: str, default: int) -> int:
        raw = os.environ.get(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from None

    return NginxConfigParams(
        upstream_host=os.environ.get("NGINX_UPSTREAM_HOST", DEFAULT_UPSTREAM_HOST),
        upstream_port=_int("NGINX_UPSTREAM_PORT", DEFAULT_UPSTREAM_PORT),
        listen_port=_int("NGINX_LISTEN_PORT", DEFAULT_LISTEN_PORT),
        segment_cache_max_age=_int("NGINX_SEGMENT_CACHE_AGE", DEFAULT_SEGMENT_CACHE_MAX_AGE),
        playlist_proxy_timeout=_int("NGINX_PLAYLIST_TIMEOUT", DEFAULT_PLAYLIST_PROXY_TIMEOUT),
        cors_origin=os.environ.get("NGINX_CORS_ORIGIN", DEFAULT_CORS_ORIGIN),
        worker_processes=os.environ.get("NGINX_WORKER_PROCESSES", "auto"),
        worker_connections=_int("NGINX_WORKER_CONNECTIONS", 1024),
        keepalive_upstream=_int("NGINX_KEEPALIVE_UPSTREAM", 32),
    )
