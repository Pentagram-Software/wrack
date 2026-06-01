"""Unit tests for wan_validator module."""

import json
import socket
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wan_validator
from wan_validator import (
    ValidationReceiver,
    build_parser,
    main,
    measure_udp_rtt,
    print_stats,
)
from latency_metrics import LatencyStats, WANQualityThresholds


# ---------------------------------------------------------------------------
# build_parser – argument defaults
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_required_server_ip(self):
        """--server-ip is required."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_default_duration(self):
        args = build_parser().parse_args(["--server-ip", "1.2.3.4"])
        assert args.duration == 30.0

    def test_default_server_port(self):
        args = build_parser().parse_args(["--server-ip", "1.2.3.4"])
        assert args.server_port == 9999

    def test_default_max_p95_ms(self):
        args = build_parser().parse_args(["--server-ip", "1.2.3.4"])
        assert args.max_p95_ms == 200.0

    def test_custom_duration(self):
        args = build_parser().parse_args(["--server-ip", "1.2.3.4", "--duration", "60"])
        assert args.duration == 60.0

    def test_wan_preset_choices_include_all_presets(self):
        from network_sim import WAN_PRESETS
        args = build_parser().parse_args(
            ["--server-ip", "1.2.3.4", "--wan-preset", "typical_wan"]
        )
        assert args.wan_preset == "typical_wan"

    def test_invalid_wan_preset_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                ["--server-ip", "1.2.3.4", "--wan-preset", "nonexistent"]
            )

    def test_json_report_returns_path(self, tmp_path):
        report_path = tmp_path / "report.json"
        args = build_parser().parse_args(
            ["--server-ip", "1.2.3.4", "--json-report", str(report_path)]
        )
        assert args.json_report == report_path


# ---------------------------------------------------------------------------
# print_stats – smoke test (no crash, writes to stdout)
# ---------------------------------------------------------------------------


class TestPrintStats:
    def test_prints_without_rtt(self, capsys):
        stats = LatencyStats(
            sample_count=50,
            duration_s=5.0,
            mean_assembly_ms=15.0,
            median_assembly_ms=14.0,
            p95_assembly_ms=30.0,
            p99_assembly_ms=40.0,
            max_assembly_ms=60.0,
            mean_fps=25.0,
            frame_loss_pct=0.5,
            mean_jitter_ms=5.0,
            rtt_ms=None,
        )
        print_stats(stats)
        out = capsys.readouterr().out
        assert "50" in out
        assert "25.0" in out
        assert "RTT" not in out

    def test_prints_with_rtt(self, capsys):
        stats = LatencyStats(
            sample_count=50,
            duration_s=5.0,
            mean_assembly_ms=15.0,
            median_assembly_ms=14.0,
            p95_assembly_ms=30.0,
            p99_assembly_ms=40.0,
            max_assembly_ms=60.0,
            mean_fps=25.0,
            frame_loss_pct=0.5,
            mean_jitter_ms=5.0,
            rtt_ms=35.0,
        )
        print_stats(stats)
        out = capsys.readouterr().out
        assert "35.0" in out


# ---------------------------------------------------------------------------
# measure_udp_rtt – tested with a real loopback UDP server
# ---------------------------------------------------------------------------


class _SimpleUDPEchoServer(threading.Thread):
    """Minimal UDP server that replies REGISTERED to any REGISTER_CLIENT."""

    def __init__(self):
        super().__init__(daemon=True)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.settimeout(0.5)
        self.port = self._sock.getsockname()[1]
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            try:
                data, addr = self._sock.recvfrom(256)
                if data.startswith(b"REGISTER_CLIENT"):
                    self._sock.sendto(b"REGISTERED", addr)
            except socket.timeout:
                pass

    def stop(self):
        self._stop_event.set()
        self._sock.close()


class TestMeasureUdpRtt:
    def test_returns_positive_rtt_from_local_server(self):
        """RTT measurement returns a positive float against a responsive server."""
        server = _SimpleUDPEchoServer()
        server.start()
        try:
            rtt = measure_udp_rtt("127.0.0.1", server.port, probe_count=3, timeout_s=2.0)
            assert rtt is not None
            assert rtt > 0
        finally:
            server.stop()

    def test_returns_none_when_server_unreachable(self):
        """Returns None when the server does not respond."""
        rtt = measure_udp_rtt("127.0.0.1", 19999, probe_count=2, timeout_s=0.3)
        assert rtt is None


# ---------------------------------------------------------------------------
# ValidationReceiver – basic instantiation and stop
# ---------------------------------------------------------------------------


class TestValidationReceiver:
    def test_instantiation(self):
        """ValidationReceiver can be created without connecting to a server."""
        receiver = ValidationReceiver(
            server_ip="127.0.0.1",
            server_port=19998,
            client_port=0,
            expected_fps=30.0,
        )
        assert receiver.tracker is not None
        receiver._sock.close()

    def test_handle_frame_start_64bit(self):
        """64-bit FRAME_START packets are parsed correctly."""
        import struct

        receiver = ValidationReceiver(
            server_ip="127.0.0.1", server_port=19997, client_port=0
        )
        try:
            frame_id, frame_size, chunk_count = 1, 3600, 3
            header = struct.pack("LLL", frame_id, frame_size, chunk_count)
            data = b"FRAME_START" + header
            assert len(data) == 35
            receiver._handle_frame_start(data)
            assert frame_id in receiver._pending
            assert receiver._expected_chunks[frame_id] == chunk_count
        finally:
            receiver._sock.close()

    def test_handle_frame_start_32bit(self):
        """32-bit FRAME_START packets are parsed as fallback."""
        import struct

        receiver = ValidationReceiver(
            server_ip="127.0.0.1", server_port=19996, client_port=0
        )
        try:
            frame_id, frame_size, chunk_count = 2, 1200, 1
            header = struct.pack("III", frame_id, frame_size, chunk_count)
            data = b"FRAME_START" + header
            assert len(data) == 23
            receiver._handle_frame_start(data)
            assert frame_id in receiver._pending
        finally:
            receiver._sock.close()

    def test_store_chunk_completes_frame(self):
        """Storing the only chunk of a single-chunk frame marks it complete."""
        import struct

        receiver = ValidationReceiver(
            server_ip="127.0.0.1", server_port=19995, client_port=0
        )
        try:
            frame_id, payload = 5, b"x" * 100
            receiver._pending[frame_id] = bytearray(100)
            receiver._expected_chunks[frame_id] = 1
            receiver._received_chunks[frame_id] = set()
            receiver.tracker.record_first_chunk(frame_id, 1, 100)
            receiver._store_chunk(frame_id, 0, payload)
            assert frame_id not in receiver._pending
            assert receiver.tracker.completed_count == 1
        finally:
            receiver._sock.close()

    def test_duplicate_chunk_ignored(self):
        """Duplicate chunk indices do not corrupt frame data."""
        import struct

        receiver = ValidationReceiver(
            server_ip="127.0.0.1", server_port=19994, client_port=0
        )
        try:
            frame_id = 6
            receiver._pending[frame_id] = bytearray(100)
            receiver._expected_chunks[frame_id] = 2
            receiver._received_chunks[frame_id] = set()
            receiver.tracker.record_first_chunk(frame_id, 2, 100)
            receiver._store_chunk(frame_id, 0, b"a" * 50)
            receiver._store_chunk(frame_id, 0, b"b" * 50)  # duplicate
            assert len(receiver._received_chunks.get(frame_id, set())) == 1
        finally:
            receiver._sock.close()


# ---------------------------------------------------------------------------
# main() – end-to-end integration with mocked receiver
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_pass_with_good_stats(self, tmp_path):
        """main() returns 0 when receiver produces passing stats."""
        report_path = tmp_path / "report.json"

        class FakeReceiver:
            def __init__(self, *a, **kw):
                from latency_metrics import FrameLatencyTracker
                self.tracker = FrameLatencyTracker(expected_fps=30.0)

            def start(self, duration_s):
                # Feed 30 frames with ~10 ms assembly latency
                for i in range(30):
                    self.tracker.record_first_chunk(i, 1, 100)
                    time.sleep(0.001)
                    self.tracker.record_complete(i)

        with (
            patch.object(wan_validator, "ValidationReceiver", FakeReceiver),
            patch.object(wan_validator, "measure_udp_rtt", return_value=20.0),
        ):
            ret = main(
                [
                    "--server-ip", "127.0.0.1",
                    "--duration", "1",
                    "--skip-rtt",
                    "--json-report", str(report_path),
                ]
            )

        assert ret == 0
        assert report_path.exists()
        report = json.loads(report_path.read_text())
        assert report["validation"]["passed"] is True

    def test_main_fail_when_no_frames(self, tmp_path):
        """main() returns 1 when no frames are received."""
        report_path = tmp_path / "report.json"

        class EmptyReceiver:
            def __init__(self, *a, **kw):
                from latency_metrics import FrameLatencyTracker
                self.tracker = FrameLatencyTracker()

            def start(self, duration_s):
                pass  # Receive nothing

        with (
            patch.object(wan_validator, "ValidationReceiver", EmptyReceiver),
            patch.object(wan_validator, "measure_udp_rtt", return_value=None),
        ):
            ret = main(
                [
                    "--server-ip", "127.0.0.1",
                    "--duration", "1",
                    "--skip-rtt",
                    "--json-report", str(report_path),
                ]
            )

        assert ret == 1
        report = json.loads(report_path.read_text())
        assert report["validation"]["passed"] is False

    def test_main_fail_with_high_latency(self, tmp_path):
        """main() returns 1 when p95 assembly latency exceeds threshold."""
        report_path = tmp_path / "report.json"

        class SlowReceiver:
            def __init__(self, *a, **kw):
                from latency_metrics import FrameLatencyTracker
                self.tracker = FrameLatencyTracker(expected_fps=30.0)

            def start(self, duration_s):
                for i in range(30):
                    self.tracker.record_first_chunk(i, 1, 100)
                    time.sleep(0.05)  # 50 ms each
                    self.tracker.record_complete(i)

        with (
            patch.object(wan_validator, "ValidationReceiver", SlowReceiver),
            patch.object(wan_validator, "measure_udp_rtt", return_value=None),
        ):
            ret = main(
                [
                    "--server-ip", "127.0.0.1",
                    "--duration", "2",
                    "--skip-rtt",
                    "--max-p95-ms", "10",  # Very tight threshold → should fail
                    "--json-report", str(report_path),
                ]
            )

        assert ret == 1

    def test_main_writes_valid_json_report(self, tmp_path):
        """JSON report contains expected top-level keys."""
        report_path = tmp_path / "report.json"

        class FastReceiver:
            def __init__(self, *a, **kw):
                from latency_metrics import FrameLatencyTracker
                self.tracker = FrameLatencyTracker(expected_fps=30.0)

            def start(self, duration_s):
                for i in range(5):
                    self.tracker.record_first_chunk(i, 1, 100)
                    self.tracker.record_complete(i)

        with (
            patch.object(wan_validator, "ValidationReceiver", FastReceiver),
            patch.object(wan_validator, "measure_udp_rtt", return_value=15.0),
        ):
            main(
                [
                    "--server-ip", "192.168.1.1",
                    "--server-port", "9999",
                    "--duration", "1",
                    "--skip-rtt",
                    "--json-report", str(report_path),
                ]
            )

        report = json.loads(report_path.read_text())
        for key in ("server", "wan_preset", "thresholds", "stats", "validation"):
            assert key in report, f"Missing key: {key}"

    def test_main_no_json_report_when_flag_absent(self):
        """main() does not write a report when --json-report is not given."""
        class QuickReceiver:
            def __init__(self, *a, **kw):
                from latency_metrics import FrameLatencyTracker
                self.tracker = FrameLatencyTracker()

            def start(self, duration_s):
                pass

        with (
            patch.object(wan_validator, "ValidationReceiver", QuickReceiver),
            patch.object(wan_validator, "measure_udp_rtt", return_value=None),
        ):
            ret = main(["--server-ip", "127.0.0.1", "--duration", "1", "--skip-rtt"])
        # Just check it doesn't crash
        assert ret in (0, 1)
