"""Stream health monitoring and HTTP health endpoint for the edge video streamer."""

import json
import logging
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import List, Optional

LOGGER = logging.getLogger("streamer.health")

# FPS window for computing rolling current FPS
_FPS_WINDOW_SECONDS = 10.0
# Below this fraction of target FPS the stream is considered degraded
_DEGRADED_FPS_RATIO = 0.5


@dataclass
class HealthSnapshot:
    """Point-in-time health metrics snapshot."""
    uptime_seconds: float
    connected_clients: int
    frames_sent: int
    current_fps: float
    error_count: int
    status: str  # "healthy" | "degraded" | "unhealthy"
    last_frame_time: Optional[float]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "connected_clients": self.connected_clients,
            "frames_sent": self.frames_sent,
            "current_fps": round(self.current_fps, 2),
            "error_count": self.error_count,
            "last_frame_age_seconds": (
                round(time.time() - self.last_frame_time, 1)
                if self.last_frame_time is not None
                else None
            ),
        }


class StreamHealthMonitor:
    """Thread-safe tracker for UDP stream health metrics.

    Usage::

        monitor = StreamHealthMonitor(target_fps=30)
        monitor.record_frame()          # call after each frame sent
        monitor.record_error()          # call on send/capture errors
        monitor.update_client_count(n)  # call when client list changes
        snap = monitor.snapshot()       # inspect current state
    """

    def __init__(self, target_fps: int = 30) -> None:
        self._target_fps = max(1, target_fps)
        self._start_time = time.time()
        self._lock = threading.Lock()
        self._total_frames: int = 0
        self._error_count: int = 0
        self._recent_frame_times: List[float] = []
        self._client_count: int = 0
        self._last_frame_time: Optional[float] = None

    # ------------------------------------------------------------------
    # Write-side API (called from streaming threads)
    # ------------------------------------------------------------------

    def record_frame(self) -> None:
        """Record that one frame was successfully sent to clients."""
        now = time.time()
        with self._lock:
            self._total_frames += 1
            self._last_frame_time = now
            self._recent_frame_times.append(now)
            self._prune_window_unlocked(now)

    def record_error(self) -> None:
        """Record one send/capture error."""
        with self._lock:
            self._error_count += 1

    def update_client_count(self, count: int) -> None:
        """Notify monitor of the current number of connected clients."""
        with self._lock:
            self._client_count = count

    # ------------------------------------------------------------------
    # Read-side API
    # ------------------------------------------------------------------

    def snapshot(self) -> HealthSnapshot:
        """Return a consistent snapshot of all health metrics."""
        with self._lock:
            now = time.time()
            self._prune_window_unlocked(now)
            fps = self._compute_fps_unlocked()
            return HealthSnapshot(
                uptime_seconds=now - self._start_time,
                connected_clients=self._client_count,
                frames_sent=self._total_frames,
                current_fps=fps,
                error_count=self._error_count,
                status=self._compute_status_unlocked(fps),
                last_frame_time=self._last_frame_time,
            )

    # ------------------------------------------------------------------
    # Internal helpers (must be called with _lock held)
    # ------------------------------------------------------------------

    def _prune_window_unlocked(self, now: float) -> None:
        cutoff = now - _FPS_WINDOW_SECONDS
        while self._recent_frame_times and self._recent_frame_times[0] < cutoff:
            self._recent_frame_times.pop(0)

    def _compute_fps_unlocked(self) -> float:
        n = len(self._recent_frame_times)
        if n < 2:
            return 0.0
        window = self._recent_frame_times[-1] - self._recent_frame_times[0]
        if window <= 0.0:
            return 0.0
        return (n - 1) / window

    def _compute_status_unlocked(self, fps: float) -> str:
        if fps <= 0.0:
            return "unhealthy"
        if fps < self._target_fps * _DEGRADED_FPS_RATIO:
            return "degraded"
        return "healthy"


class _HealthRequestHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for the /health endpoint."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            body = json.dumps(self.server.monitor.snapshot().to_dict()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: ANN002
        LOGGER.debug(fmt, *args)


class HealthServer:
    """Lightweight HTTP server that exposes a ``/health`` JSON endpoint.

    Run alongside a :class:`StreamHealthMonitor`::

        monitor = StreamHealthMonitor(target_fps=30)
        server = HealthServer(monitor, port=8090)
        server.start()
        # … stream frames …
        server.stop()
    """

    def __init__(
        self,
        monitor: StreamHealthMonitor,
        host: str = "0.0.0.0",
        port: int = 8090,
    ) -> None:
        self._monitor = monitor
        self._host = host
        self._port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        """Start the health HTTP server in a daemon background thread."""
        httpd = HTTPServer((self._host, self._port), _HealthRequestHandler)
        httpd.monitor = self._monitor  # type: ignore[attr-defined]
        self._server = httpd

        self._thread = threading.Thread(
            target=httpd.serve_forever, name="health-http", daemon=True
        )
        self._thread.start()
        LOGGER.info("Health endpoint started at http://%s:%d/health", self._host, self._port)

    def stop(self) -> None:
        """Shut down the health HTTP server."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
