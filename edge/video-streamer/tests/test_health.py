"""Unit tests for health.py — StreamStats and HealthServer."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

import pytest

from health import HealthServer, StreamStats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def stats() -> StreamStats:
    return StreamStats()


@pytest.fixture()
def running_server(stats: StreamStats):
    """Spin up a HealthServer on a free port; tear it down after the test."""
    port = _free_port()
    server = HealthServer(stats, host="127.0.0.1", port=port)
    server.start()
    time.sleep(0.05)  # give the daemon thread a moment to bind
    yield server, port
    server.stop()


def _get(port: int, path: str = "/health") -> tuple[int, dict | None]:
    """HTTP GET helper; returns (status_code, parsed_body_or_None)."""
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except Exception:
            body = None
        return exc.code, body


# ===========================================================================
# StreamStats tests
# ===========================================================================


class TestStreamStatsDefaults:
    def test_transport_empty(self, stats: StreamStats):
        assert stats.transport == ""

    def test_streaming_active_false(self, stats: StreamStats):
        assert stats.streaming_active is False

    def test_camera_ready_false(self, stats: StreamStats):
        assert stats.camera_ready is False

    def test_frames_sent_zero(self, stats: StreamStats):
        assert stats.frames_sent == 0

    def test_clients_connected_zero(self, stats: StreamStats):
        assert stats.clients_connected == 0

    def test_errors_zero(self, stats: StreamStats):
        assert stats.errors == 0

    def test_fps_zero(self, stats: StreamStats):
        assert stats.fps == 0.0

    def test_uptime_non_negative(self, stats: StreamStats):
        assert stats.uptime_seconds >= 0.0


class TestStreamStatsRecordFrame:
    def test_increments_frames_sent(self, stats: StreamStats):
        stats.record_frame()
        stats.record_frame()
        stats.record_frame()
        assert stats.frames_sent == 3

    def test_fps_updates_after_window_elapsed(self, stats: StreamStats):
        # Force the window to appear as if 5+ seconds have passed so the
        # FPS computation fires on the next record_frame() call.
        stats._fps_window_start = time.time() - 5.5
        stats._fps_window_frames = 30
        stats.record_frame()  # triggers the flush
        assert stats.fps > 0.0

    def test_fps_window_reset_after_flush(self, stats: StreamStats):
        stats._fps_window_start = time.time() - 5.5
        stats._fps_window_frames = 30
        stats.record_frame()
        # The triggering frame is counted into the closed window's FPS value,
        # then the counter resets to 0 for the next window.
        assert stats._fps_window_frames == 0


class TestStreamStatsToDict:
    def test_contains_required_keys(self, stats: StreamStats):
        required = {
            "status",
            "camera_ready",
            "streaming_active",
            "transport",
            "uptime_seconds",
            "clients_connected",
            "fps",
            "frames_sent",
            "errors",
        }
        assert required.issubset(stats.to_dict().keys())

    def test_status_is_ok(self, stats: StreamStats):
        assert stats.to_dict()["status"] == "ok"

    def test_reflects_mutations(self, stats: StreamStats):
        stats.camera_ready = True
        stats.streaming_active = True
        stats.transport = "udp"
        stats.clients_connected = 3
        stats.errors = 2
        stats.record_frame()

        d = stats.to_dict()
        assert d["camera_ready"] is True
        assert d["streaming_active"] is True
        assert d["transport"] == "udp"
        assert d["clients_connected"] == 3
        assert d["errors"] == 2
        assert d["frames_sent"] == 1

    def test_uptime_seconds_non_negative(self, stats: StreamStats):
        assert stats.to_dict()["uptime_seconds"] >= 0.0

    def test_uptime_seconds_is_float(self, stats: StreamStats):
        assert isinstance(stats.to_dict()["uptime_seconds"], float)

    def test_fps_is_numeric(self, stats: StreamStats):
        d = stats.to_dict()
        assert isinstance(d["fps"], (int, float))

    def test_frames_sent_matches_record_frame_calls(self, stats: StreamStats):
        for _ in range(7):
            stats.record_frame()
        assert stats.to_dict()["frames_sent"] == 7


class TestStreamStatsProperties:
    def test_uptime_property_non_negative(self, stats: StreamStats):
        assert stats.uptime_seconds >= 0.0

    def test_fps_property_zero_initially(self, stats: StreamStats):
        assert stats.fps == 0.0


# ===========================================================================
# HealthServer tests
# ===========================================================================


class TestHealthServerResponses:
    def test_health_returns_200(self, running_server):
        _, port = running_server
        status, _ = _get(port)
        assert status == 200

    def test_health_response_is_json_dict(self, running_server):
        _, port = running_server
        _, body = _get(port)
        assert isinstance(body, dict)

    def test_health_status_ok(self, running_server):
        _, port = running_server
        _, body = _get(port)
        assert body["status"] == "ok"

    def test_unknown_path_returns_404(self, running_server):
        _, port = running_server
        status, _ = _get(port, "/unknown")
        assert status == 404

    def test_404_body_is_json(self, running_server):
        _, port = running_server
        _, body = _get(port, "/nonexistent")
        assert isinstance(body, dict)


class TestHealthServerReflectsStats:
    def test_camera_ready_reflected(self, stats: StreamStats, running_server):
        _, port = running_server
        stats.camera_ready = True
        _, body = _get(port)
        assert body["camera_ready"] is True

    def test_streaming_active_reflected(self, stats: StreamStats, running_server):
        _, port = running_server
        stats.streaming_active = True
        _, body = _get(port)
        assert body["streaming_active"] is True

    def test_transport_reflected(self, stats: StreamStats, running_server):
        _, port = running_server
        stats.transport = "udp"
        _, body = _get(port)
        assert body["transport"] == "udp"

    def test_clients_connected_reflected(self, stats: StreamStats, running_server):
        _, port = running_server
        stats.clients_connected = 5
        _, body = _get(port)
        assert body["clients_connected"] == 5

    def test_frames_sent_reflected(self, stats: StreamStats, running_server):
        _, port = running_server
        stats.record_frame()
        stats.record_frame()
        _, body = _get(port)
        assert body["frames_sent"] == 2

    def test_errors_reflected(self, stats: StreamStats, running_server):
        _, port = running_server
        stats.errors = 3
        _, body = _get(port)
        assert body["errors"] == 3


class TestHealthServerLifecycle:
    def test_start_and_stop(self, stats: StreamStats):
        port = _free_port()
        server = HealthServer(stats, host="127.0.0.1", port=port)
        server.start()
        time.sleep(0.05)
        status, _ = _get(port)
        assert status == 200
        server.stop()

    def test_stop_twice_does_not_raise(self, stats: StreamStats):
        port = _free_port()
        server = HealthServer(stats, host="127.0.0.1", port=port)
        server.start()
        time.sleep(0.05)
        server.stop()
        server.stop()  # second call must be safe

    def test_server_unreachable_after_stop(self, stats: StreamStats):
        port = _free_port()
        server = HealthServer(stats, host="127.0.0.1", port=port)
        server.start()
        time.sleep(0.05)
        server.stop()
        time.sleep(0.05)
        with pytest.raises((ConnectionRefusedError, OSError)):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
