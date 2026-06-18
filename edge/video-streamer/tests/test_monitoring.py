"""
Unit tests for edge/video-streamer/monitoring.py.

All file I/O is performed against a temporary directory so no real
filesystem paths (/var/lib/grafana-alloy/…) are touched during testing.
"""

import os
import re

import pytest

from monitoring import (
    DEFAULT_TEXTFILE_PATH,
    StreamMetrics,
    write_metrics,
    write_stopped_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_prom(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _metric_value(content: str, metric_name: str) -> str:
    """Extract the first value for a bare metric name (no labels)."""
    pattern = rf"^{re.escape(metric_name)}\s+(\S+)"
    m = re.search(pattern, content, re.MULTILINE)
    assert m is not None, f"{metric_name!r} not found in:\n{content}"
    return m.group(1)


# ---------------------------------------------------------------------------
# StreamMetrics
# ---------------------------------------------------------------------------

class TestStreamMetrics:
    def test_fields_stored(self):
        m = StreamMetrics(
            alive=True,
            fps_recent=29.5,
            frame_drop_total=3,
            client_count=2,
            uptime_seconds=120.0,
        )
        assert m.alive is True
        assert m.fps_recent == pytest.approx(29.5)
        assert m.frame_drop_total == 3
        assert m.client_count == 2
        assert m.uptime_seconds == pytest.approx(120.0)

    def test_alive_false(self):
        m = StreamMetrics(
            alive=False,
            fps_recent=0.0,
            frame_drop_total=0,
            client_count=0,
            uptime_seconds=0.0,
        )
        assert m.alive is False


# ---------------------------------------------------------------------------
# write_metrics — basic output shape
# ---------------------------------------------------------------------------

class TestWriteMetrics:
    def test_creates_file(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        metrics = StreamMetrics(
            alive=True,
            fps_recent=29.7,
            frame_drop_total=5,
            client_count=3,
            uptime_seconds=300.0,
        )
        write_metrics(metrics, path=dest)
        assert os.path.exists(dest)

    def test_alive_gauge_is_1_when_running(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_metrics(
            StreamMetrics(True, 25.0, 0, 1, 10.0),
            path=dest,
        )
        content = _read_prom(dest)
        assert _metric_value(content, "wrack_stream_alive") == "1"

    def test_alive_gauge_is_0_when_stopped(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_metrics(
            StreamMetrics(False, 0.0, 0, 0, 60.0),
            path=dest,
        )
        content = _read_prom(dest)
        assert _metric_value(content, "wrack_stream_alive") == "0"

    def test_fps_recent_value(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_metrics(
            StreamMetrics(True, 29.987, 0, 1, 10.0),
            path=dest,
        )
        content = _read_prom(dest)
        assert float(_metric_value(content, "wrack_stream_fps_recent")) == pytest.approx(29.987, rel=1e-3)

    def test_frame_drop_total_value(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_metrics(
            StreamMetrics(True, 30.0, 7, 2, 120.0),
            path=dest,
        )
        content = _read_prom(dest)
        assert int(_metric_value(content, "wrack_stream_frame_drop_total")) == 7

    def test_client_count_value(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_metrics(
            StreamMetrics(True, 30.0, 0, 4, 120.0),
            path=dest,
        )
        content = _read_prom(dest)
        assert int(_metric_value(content, "wrack_stream_client_count")) == 4

    def test_uptime_seconds_value(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_metrics(
            StreamMetrics(True, 30.0, 0, 1, 3600.5),
            path=dest,
        )
        content = _read_prom(dest)
        assert float(_metric_value(content, "wrack_stream_uptime_seconds")) == pytest.approx(3600.5, rel=1e-3)

    def test_help_and_type_lines_present(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_metrics(
            StreamMetrics(True, 30.0, 0, 1, 10.0),
            path=dest,
        )
        content = _read_prom(dest)
        assert "# HELP wrack_stream_alive" in content
        assert "# TYPE wrack_stream_alive gauge" in content
        assert "# HELP wrack_stream_fps_recent" in content
        assert "# TYPE wrack_stream_fps_recent gauge" in content
        assert "# HELP wrack_stream_frame_drop_total" in content
        assert "# TYPE wrack_stream_frame_drop_total counter" in content
        assert "# HELP wrack_stream_client_count" in content
        assert "# TYPE wrack_stream_client_count gauge" in content
        assert "# HELP wrack_stream_uptime_seconds" in content
        assert "# TYPE wrack_stream_uptime_seconds gauge" in content

    def test_all_five_metrics_present(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_metrics(
            StreamMetrics(True, 30.0, 1, 2, 60.0),
            path=dest,
        )
        content = _read_prom(dest)
        for metric in [
            "wrack_stream_alive",
            "wrack_stream_fps_recent",
            "wrack_stream_frame_drop_total",
            "wrack_stream_client_count",
            "wrack_stream_uptime_seconds",
        ]:
            assert metric in content, f"Expected metric {metric!r} in output"

    def test_creates_parent_directories(self, tmp_path):
        dest = str(tmp_path / "nested" / "dir" / "video_stream.prom")
        write_metrics(
            StreamMetrics(True, 30.0, 0, 1, 10.0),
            path=dest,
        )
        assert os.path.exists(dest)

    def test_atomic_write_no_tmp_file_left(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_metrics(
            StreamMetrics(True, 30.0, 0, 1, 10.0),
            path=dest,
        )
        assert not os.path.exists(dest + ".tmp")

    def test_overwrite_updates_values(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_metrics(StreamMetrics(True, 10.0, 0, 1, 5.0), path=dest)
        write_metrics(StreamMetrics(True, 28.3, 2, 3, 15.0), path=dest)
        content = _read_prom(dest)
        assert float(_metric_value(content, "wrack_stream_fps_recent")) == pytest.approx(28.3, rel=1e-3)
        assert int(_metric_value(content, "wrack_stream_frame_drop_total")) == 2
        assert int(_metric_value(content, "wrack_stream_client_count")) == 3

    def test_zero_fps_is_valid(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_metrics(
            StreamMetrics(True, 0.0, 0, 0, 0.0),
            path=dest,
        )
        content = _read_prom(dest)
        assert float(_metric_value(content, "wrack_stream_fps_recent")) == 0.0


# ---------------------------------------------------------------------------
# write_stopped_metrics
# ---------------------------------------------------------------------------

class TestWriteStoppedMetrics:
    def test_alive_is_0(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_stopped_metrics(path=dest)
        content = _read_prom(dest)
        assert _metric_value(content, "wrack_stream_alive") == "0"

    def test_client_count_is_0(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_stopped_metrics(path=dest)
        content = _read_prom(dest)
        assert int(_metric_value(content, "wrack_stream_client_count")) == 0

    def test_fps_recent_is_0(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_stopped_metrics(path=dest)
        content = _read_prom(dest)
        assert float(_metric_value(content, "wrack_stream_fps_recent")) == 0.0

    def test_preserves_frame_drop_total(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_stopped_metrics(frame_drop_total=12, path=dest)
        content = _read_prom(dest)
        assert int(_metric_value(content, "wrack_stream_frame_drop_total")) == 12

    def test_preserves_uptime_seconds(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_stopped_metrics(uptime_seconds=450.0, path=dest)
        content = _read_prom(dest)
        assert float(_metric_value(content, "wrack_stream_uptime_seconds")) == pytest.approx(450.0, rel=1e-3)

    def test_defaults_are_zero(self, tmp_path):
        dest = str(tmp_path / "video_stream.prom")
        write_stopped_metrics(path=dest)
        content = _read_prom(dest)
        assert int(_metric_value(content, "wrack_stream_frame_drop_total")) == 0
        assert float(_metric_value(content, "wrack_stream_uptime_seconds")) == 0.0

    def test_creates_file_if_not_exists(self, tmp_path):
        dest = str(tmp_path / "new_dir" / "video_stream.prom")
        write_stopped_metrics(path=dest)
        assert os.path.exists(dest)


# ---------------------------------------------------------------------------
# DEFAULT_TEXTFILE_PATH constant
# ---------------------------------------------------------------------------

class TestDefaultPath:
    def test_default_path_value(self):
        assert DEFAULT_TEXTFILE_PATH == "/var/lib/grafana-alloy/textfile/video_stream.prom"
