"""Health endpoint, streaming statistics, and logging utilities.

This module contains no hardware dependencies and is fully unit-testable
in any Python environment, including CI without a real Raspberry Pi camera.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer

LOGGER = logging.getLogger("streamer")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def configure_logging(
    log_path: str = "logs/streamer.log",
    level: int = logging.INFO,
    console: bool = True,
) -> None:
    """Configure the streamer logger with file and/or console handlers.

    Idempotent: a second call while handlers are already registered is a
    no-op so that calling configure_logging() multiple times (e.g. in tests
    or repeated imports) is safe.

    Args:
        log_path: Path to the log file.  Set to ``""`` to skip file logging.
        level:    Logging level (e.g. ``logging.INFO``, ``logging.DEBUG``).
        console:  When *True* a StreamHandler that writes to stderr is added
                  in addition to the file handler.
    """
    if LOGGER.handlers:
        return
    LOGGER.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s")
    if log_path:
        log_dir = os.path.dirname(log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(fmt)
        LOGGER.addHandler(file_handler)
    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(fmt)
        LOGGER.addHandler(stream_handler)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class StreamStats:
    """Thread-safe container for streaming health and performance metrics.

    Public fields may be written from the streaming thread at any time.
    Call ``record_frame()`` for every successfully sent frame so that the
    rolling FPS window is maintained.  Use ``to_dict()`` to produce the
    health-endpoint JSON payload.
    """

    transport: str = ""
    streaming_active: bool = False
    camera_ready: bool = False
    frames_sent: int = 0
    clients_connected: int = 0
    errors: int = 0

    def __post_init__(self) -> None:
        self._start_time: float = time.time()
        self._fps_window_start: float = time.time()
        self._fps_window_frames: int = 0
        self._fps: float = 0.0
        self._lock = threading.Lock()

    def record_frame(self) -> None:
        """Increment ``frames_sent`` and refresh the rolling FPS estimate.

        The FPS window is flushed every 5 seconds; between flushes the
        ``fps`` property returns the value from the previous window.
        """
        with self._lock:
            self.frames_sent += 1
            self._fps_window_frames += 1
            now = time.time()
            elapsed = now - self._fps_window_start
            if elapsed >= 5.0:
                self._fps = self._fps_window_frames / elapsed
                self._fps_window_start = now
                self._fps_window_frames = 0

    @property
    def uptime_seconds(self) -> float:
        """Seconds elapsed since this ``StreamStats`` instance was created."""
        return round(time.time() - self._start_time, 1)

    @property
    def fps(self) -> float:
        """Most recently computed rolling FPS (updated every 5 s)."""
        with self._lock:
            return round(self._fps, 1)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable snapshot of the current health status."""
        with self._lock:
            return {
                "status": "ok",
                "camera_ready": self.camera_ready,
                "streaming_active": self.streaming_active,
                "transport": self.transport,
                "uptime_seconds": round(time.time() - self._start_time, 1),
                "clients_connected": self.clients_connected,
                "fps": round(self._fps, 1),
                "frames_sent": self.frames_sent,
                "errors": self.errors,
            }


# ---------------------------------------------------------------------------
# Health HTTP server
# ---------------------------------------------------------------------------


class HealthServer:
    """Lightweight HTTP server that exposes ``GET /health`` as a JSON check.

    Runs in a background daemon thread so it does not block the streaming
    loop.  Stats are read from the provided :class:`StreamStats` instance on
    every request — no copying, no caching.

    Example::

        stats = StreamStats()
        health = HealthServer(stats, port=9000)
        health.start()
        # … streaming loop …
        health.stop()
    """

    def __init__(
        self,
        stats: StreamStats,
        host: str = "0.0.0.0",
        port: int = 9000,
    ) -> None:
        self.stats = stats
        self.host = host
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_handler_class(self) -> type:
        stats = self.stats

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 — HTTP method name
                if self.path == "/health":
                    body = json.dumps(stats.to_dict()).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    body = json.dumps({"error": "not found"}).encode()
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            def log_message(self, fmt: str, *args: object) -> None:
                LOGGER.debug("health %s - %s", self.address_string(), fmt % args)

        return _Handler

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the health HTTP server in a background daemon thread."""
        self._server = HTTPServer((self.host, self.port), self._make_handler_class())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="health-server",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info(
            "Health server listening on http://%s:%s/health", self.host, self.port
        )

    def stop(self) -> None:
        """Gracefully shut down the health HTTP server."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        LOGGER.info("Health server stopped")
