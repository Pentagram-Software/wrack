"""
Prometheus textfile writer for video stream health metrics.

Writes Prometheus exposition-format metrics to a textfile that is scraped
by Grafana Alloy's ``prometheus.exporter.unix`` textfile collector.

The textfile is updated atomically (write to ``.tmp``, then ``os.replace``)
so Alloy never reads a partial file.

Default path: /var/lib/grafana-alloy/textfile/video_stream.prom
Updated every ``status_interval`` seconds from inside UDPVideoStreamer.

Exposed metrics
---------------
wrack_stream_alive          gauge   1 = streaming, 0 = stopped
wrack_stream_fps_recent     gauge   FPS over the last status interval
wrack_stream_frame_drop_total counter cumulative failed client sends
wrack_stream_client_count   gauge   current connected clients
wrack_stream_uptime_seconds gauge   seconds since streamer start
"""

from __future__ import annotations

import os
import time
from typing import Optional

DEFAULT_TEXTFILE_PATH = "/var/lib/grafana-alloy/textfile/video_stream.prom"


class StreamMetrics:
    """Snapshot of stream metrics passed to :func:`write_metrics`."""

    __slots__ = (
        "alive",
        "fps_recent",
        "frame_drop_total",
        "client_count",
        "uptime_seconds",
    )

    def __init__(
        self,
        alive: bool,
        fps_recent: float,
        frame_drop_total: int,
        client_count: int,
        uptime_seconds: float,
    ) -> None:
        self.alive = alive
        self.fps_recent = fps_recent
        self.frame_drop_total = frame_drop_total
        self.client_count = client_count
        self.uptime_seconds = uptime_seconds


def write_metrics(
    metrics: StreamMetrics,
    path: str = DEFAULT_TEXTFILE_PATH,
) -> None:
    """Atomically write Prometheus textfile metrics to *path*.

    Creates parent directories as needed.  Writes to ``<path>.tmp`` first,
    then renames to *path* to guarantee Alloy never reads a partial file.

    Parameters
    ----------
    metrics:
        Current stream metric values to expose.
    path:
        Destination textfile path.  Defaults to
        ``/var/lib/grafana-alloy/textfile/video_stream.prom``.

    Raises
    ------
    OSError
        If the directory cannot be created or the file cannot be written.
    """
    alive_value = 1 if metrics.alive else 0
    content = (
        "# HELP wrack_stream_alive 1 if the video streamer is running, 0 if stopped\n"
        "# TYPE wrack_stream_alive gauge\n"
        f"wrack_stream_alive {alive_value}\n"
        "\n"
        "# HELP wrack_stream_fps_recent Frames per second over the last status interval\n"
        "# TYPE wrack_stream_fps_recent gauge\n"
        f"wrack_stream_fps_recent {metrics.fps_recent:.3f}\n"
        "\n"
        "# HELP wrack_stream_frame_drop_total Cumulative count of failed client frame sends\n"
        "# TYPE wrack_stream_frame_drop_total counter\n"
        f"wrack_stream_frame_drop_total {metrics.frame_drop_total}\n"
        "\n"
        "# HELP wrack_stream_client_count Current number of connected streaming clients\n"
        "# TYPE wrack_stream_client_count gauge\n"
        f"wrack_stream_client_count {metrics.client_count}\n"
        "\n"
        "# HELP wrack_stream_uptime_seconds Seconds since the streamer process started\n"
        "# TYPE wrack_stream_uptime_seconds gauge\n"
        f"wrack_stream_uptime_seconds {metrics.uptime_seconds:.3f}\n"
    )

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp_path, path)


def write_stopped_metrics(
    frame_drop_total: int = 0,
    uptime_seconds: float = 0.0,
    path: str = DEFAULT_TEXTFILE_PATH,
) -> None:
    """Write final metrics indicating the streamer has stopped (alive=0).

    Convenience wrapper around :func:`write_metrics` that sets all
    activity counters to zero and marks the stream as not alive.

    Parameters
    ----------
    frame_drop_total:
        Cumulative frame drop count at the time of stop.
    uptime_seconds:
        Total uptime before stopping.
    path:
        Destination textfile path.
    """
    metrics = StreamMetrics(
        alive=False,
        fps_recent=0.0,
        frame_drop_total=frame_drop_total,
        client_count=0,
        uptime_seconds=uptime_seconds,
    )
    write_metrics(metrics, path=path)
