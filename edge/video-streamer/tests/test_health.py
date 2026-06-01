"""Unit tests for edge/video-streamer/health.py."""

import json
import threading
import time
import urllib.request

import pytest

from health import HealthServer, HealthSnapshot, StreamHealthMonitor


# ---------------------------------------------------------------------------
# StreamHealthMonitor tests
# ---------------------------------------------------------------------------

class TestStreamHealthMonitorInitialState:
    def test_initial_snapshot_status_is_unhealthy(self):
        monitor = StreamHealthMonitor(target_fps=30)
        snap = monitor.snapshot()
        assert snap.status == "unhealthy"

    def test_initial_frames_sent_is_zero(self):
        monitor = StreamHealthMonitor(target_fps=30)
        snap = monitor.snapshot()
        assert snap.frames_sent == 0

    def test_initial_error_count_is_zero(self):
        monitor = StreamHealthMonitor(target_fps=30)
        snap = monitor.snapshot()
        assert snap.error_count == 0

    def test_initial_connected_clients_is_zero(self):
        monitor = StreamHealthMonitor(target_fps=30)
        snap = monitor.snapshot()
        assert snap.connected_clients == 0

    def test_initial_current_fps_is_zero(self):
        monitor = StreamHealthMonitor(target_fps=30)
        snap = monitor.snapshot()
        assert snap.current_fps == 0.0

    def test_initial_last_frame_time_is_none(self):
        monitor = StreamHealthMonitor(target_fps=30)
        snap = monitor.snapshot()
        assert snap.last_frame_time is None

    def test_uptime_increases_over_time(self):
        monitor = StreamHealthMonitor()
        time.sleep(0.05)
        snap = monitor.snapshot()
        assert snap.uptime_seconds >= 0.0


class TestStreamHealthMonitorRecordFrame:
    def test_record_frame_increments_frames_sent(self):
        monitor = StreamHealthMonitor()
        monitor.record_frame()
        monitor.record_frame()
        assert monitor.snapshot().frames_sent == 2

    def test_record_frame_sets_last_frame_time(self):
        monitor = StreamHealthMonitor()
        before = time.time()
        monitor.record_frame()
        after = time.time()
        snap = monitor.snapshot()
        assert snap.last_frame_time is not None
        assert before <= snap.last_frame_time <= after

    def test_fps_computed_from_multiple_frames(self):
        monitor = StreamHealthMonitor(target_fps=30)
        # Record 11 frames with known 0.1s spacing → ~10 FPS
        for _ in range(11):
            monitor.record_frame()
            time.sleep(0.1)
        fps = monitor.snapshot().current_fps
        assert 8.0 <= fps <= 12.0, f"Expected ~10 FPS, got {fps}"

    def test_single_frame_fps_is_zero(self):
        """One frame is not enough to compute FPS (need at least 2 timestamps)."""
        monitor = StreamHealthMonitor()
        monitor.record_frame()
        assert monitor.snapshot().current_fps == 0.0


class TestStreamHealthMonitorStatus:
    def test_healthy_when_fps_above_half_target(self):
        monitor = StreamHealthMonitor(target_fps=10)
        # Record 11 frames over ~1 s → ~10 FPS, well above 5 FPS threshold
        for _ in range(11):
            monitor.record_frame()
            time.sleep(0.1)
        assert monitor.snapshot().status == "healthy"

    def test_degraded_when_fps_below_half_target(self):
        monitor = StreamHealthMonitor(target_fps=20)
        # Record 11 frames over ~2 s → ~5 FPS, below 10 FPS threshold (50% of 20)
        for _ in range(11):
            monitor.record_frame()
            time.sleep(0.2)
        snap = monitor.snapshot()
        assert snap.status in ("degraded", "unhealthy"), (
            f"Expected degraded/unhealthy but got {snap.status} (fps={snap.current_fps})"
        )

    def test_unhealthy_when_no_frames(self):
        monitor = StreamHealthMonitor(target_fps=30)
        assert monitor.snapshot().status == "unhealthy"


class TestStreamHealthMonitorErrorCount:
    def test_record_error_increments_count(self):
        monitor = StreamHealthMonitor()
        monitor.record_error()
        monitor.record_error()
        assert monitor.snapshot().error_count == 2


class TestStreamHealthMonitorClientCount:
    def test_update_client_count(self):
        monitor = StreamHealthMonitor()
        monitor.update_client_count(3)
        assert monitor.snapshot().connected_clients == 3

    def test_update_client_count_to_zero(self):
        monitor = StreamHealthMonitor()
        monitor.update_client_count(5)
        monitor.update_client_count(0)
        assert monitor.snapshot().connected_clients == 0


class TestStreamHealthMonitorThreadSafety:
    def test_concurrent_record_frame_is_safe(self):
        monitor = StreamHealthMonitor()
        errors: list = []

        def writer():
            try:
                for _ in range(50):
                    monitor.record_frame()
                    time.sleep(0.001)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert monitor.snapshot().frames_sent == 200


# ---------------------------------------------------------------------------
# HealthSnapshot.to_dict tests
# ---------------------------------------------------------------------------

class TestHealthSnapshotToDict:
    def _make_snapshot(self, **overrides) -> HealthSnapshot:
        defaults = dict(
            uptime_seconds=42.123,
            connected_clients=2,
            frames_sent=300,
            current_fps=29.5,
            error_count=1,
            status="healthy",
            last_frame_time=time.time() - 0.5,
        )
        defaults.update(overrides)
        return HealthSnapshot(**defaults)

    def test_to_dict_contains_required_keys(self):
        snap = self._make_snapshot()
        d = snap.to_dict()
        for key in ("status", "uptime_seconds", "connected_clients", "frames_sent",
                    "current_fps", "error_count", "last_frame_age_seconds"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_none_last_frame_time(self):
        snap = self._make_snapshot(last_frame_time=None)
        assert snap.to_dict()["last_frame_age_seconds"] is None

    def test_to_dict_last_frame_age_is_non_negative(self):
        snap = self._make_snapshot(last_frame_time=time.time() - 2.0)
        age = snap.to_dict()["last_frame_age_seconds"]
        assert age >= 0.0

    def test_to_dict_is_json_serialisable(self):
        snap = self._make_snapshot()
        json.dumps(snap.to_dict())  # must not raise


# ---------------------------------------------------------------------------
# HealthServer tests
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    import socket as _socket
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestHealthServer:
    def test_health_endpoint_returns_200(self):
        monitor = StreamHealthMonitor()
        port = _find_free_port()
        server = HealthServer(monitor, host="127.0.0.1", port=port)
        server.start()
        try:
            time.sleep(0.1)  # allow thread to bind
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as resp:
                assert resp.status == 200
        finally:
            server.stop()

    def test_health_endpoint_returns_json(self):
        monitor = StreamHealthMonitor()
        port = _find_free_port()
        server = HealthServer(monitor, host="127.0.0.1", port=port)
        server.start()
        try:
            time.sleep(0.1)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as resp:
                body = json.loads(resp.read())
            assert isinstance(body, dict)
            assert "status" in body
        finally:
            server.stop()

    def test_health_endpoint_reflects_monitor_state(self):
        monitor = StreamHealthMonitor()
        monitor.update_client_count(3)
        port = _find_free_port()
        server = HealthServer(monitor, host="127.0.0.1", port=port)
        server.start()
        try:
            time.sleep(0.1)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as resp:
                body = json.loads(resp.read())
            assert body["connected_clients"] == 3
        finally:
            server.stop()

    def test_unknown_path_returns_404(self):
        monitor = StreamHealthMonitor()
        port = _find_free_port()
        server = HealthServer(monitor, host="127.0.0.1", port=port)
        server.start()
        try:
            time.sleep(0.1)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/unknown")
            assert exc_info.value.code == 404
        finally:
            server.stop()

    def test_server_port_property(self):
        monitor = StreamHealthMonitor()
        server = HealthServer(monitor, port=9876)
        assert server.port == 9876
