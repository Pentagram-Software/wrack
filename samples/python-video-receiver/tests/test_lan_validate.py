"""Unit tests for receiver.lan_validate.

Tests cover:
  - compute_report(): pure report-computation function
  - _compute_frame_loss_pct(): frame-id gap analysis
  - _compute_jitter_ms(): standard deviation of inter-frame intervals
  - ValidationReport.summary(): human-readable output
  - LanValidator packet parsing (_handle_frame_start, _handle_chunk)
  - LanValidator frame assembly and sample collection
  - LanValidator._register() error handling
  - CLI argument parsing via main()
"""

from __future__ import annotations

import math
import socket
import struct
import threading
import time
import unittest

from receiver.lan_validate import (
    TARGET_E2E_LATENCY_MS,
    TARGET_FPS_MARGIN,
    TARGET_FRAME_LOSS_PCT,
    TARGET_JITTER_MS,
    FrameSample,
    LanValidator,
    ValidationReport,
    _compute_frame_loss_pct,
    _compute_jitter_ms,
    compute_report,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sample(
    frame_id: int = 0,
    first_mono: float = 0.0,
    last_mono: float = 0.010,
    first_wall: float = 1_000_000.0,
    last_wall: float = 1_000_000.010,
    server_ts_us: int | None = None,
) -> FrameSample:
    return FrameSample(
        frame_id=frame_id,
        first_chunk_wall=first_wall,
        last_chunk_wall=last_wall,
        first_chunk_mono=first_mono,
        last_chunk_mono=last_mono,
        server_ts_us=server_ts_us,
    )


def _perfect_samples(
    n: int = 30,
    interval_s: float = 1 / 30,
    assembly_s: float = 0.005,
) -> list[FrameSample]:
    """Generate n evenly-spaced samples with low assembly time."""
    samples = []
    base_mono = 1.0
    base_wall = 1_700_000_000.0
    for i in range(n):
        t0_mono = base_mono + i * interval_s
        t1_mono = t0_mono + assembly_s
        t0_wall = base_wall + i * interval_s
        t1_wall = t0_wall + assembly_s
        samples.append(
            _make_sample(
                frame_id=i,
                first_mono=t0_mono,
                last_mono=t1_mono,
                first_wall=t0_wall,
                last_wall=t1_wall,
            )
        )
    return samples


# ---------------------------------------------------------------------------
# compute_report — pass scenarios
# ---------------------------------------------------------------------------


class TestComputeReportPass(unittest.TestCase):
    def test_perfect_stream_passes_all_targets(self):
        """30 evenly-spaced frames in 1 s at 30 fps with 5 ms assembly → all PASS."""
        samples = _perfect_samples(n=30, interval_s=1 / 30, assembly_s=0.005)
        report = compute_report(samples, duration_s=1.0, target_fps=30.0)

        self.assertTrue(report.fps_ok, f"fps_ok False, actual_fps={report.actual_fps}")
        self.assertTrue(report.frame_loss_ok)
        self.assertTrue(report.e2e_latency_ok)
        self.assertTrue(report.jitter_ok)
        self.assertTrue(report.passed)

    def test_frames_received_and_expected(self):
        samples = _perfect_samples(n=15)
        report = compute_report(samples, duration_s=0.5, target_fps=30.0)
        self.assertEqual(report.frames_received, 15)
        self.assertEqual(report.frames_expected, 15)

    def test_actual_fps_computed_correctly(self):
        samples = _perfect_samples(n=60)
        report = compute_report(samples, duration_s=2.0, target_fps=30.0)
        self.assertAlmostEqual(report.actual_fps, 30.0, places=1)

    def test_avg_assembly_ms_correct(self):
        samples = _perfect_samples(n=10, assembly_s=0.020)
        report = compute_report(samples, duration_s=10 / 30, target_fps=30.0)
        self.assertAlmostEqual(report.avg_assembly_ms, 20.0, places=1)

    def test_latency_source_assembly_when_no_server_timestamps(self):
        samples = _perfect_samples(n=10)
        report = compute_report(samples, duration_s=10 / 30, target_fps=30.0)
        self.assertEqual(report.latency_source, "assembly")

    def test_latency_source_server_timestamp_when_present(self):
        base_wall = 1_700_000_000.0
        server_ts_us = int((base_wall - 0.030) * 1_000_000)  # 30 ms before receive
        samples = [
            _make_sample(
                frame_id=i,
                first_wall=base_wall + i * 0.033,
                last_wall=base_wall + i * 0.033 + 0.030,
                server_ts_us=server_ts_us + i * 33_000,
            )
            for i in range(10)
        ]
        report = compute_report(samples, duration_s=10 * 0.033, target_fps=30.0)
        self.assertEqual(report.latency_source, "server_timestamp")

    def test_server_timestamp_e2e_latency_approx(self):
        """E2E latency should be close to 30 ms when timestamps say 30 ms ago."""
        base_wall = 1_700_000_000.0
        latency_s = 0.030  # 30 ms
        samples = [
            _make_sample(
                frame_id=i,
                first_wall=base_wall + i * 0.033,
                last_wall=base_wall + i * 0.033 + latency_s,
                server_ts_us=int((base_wall + i * 0.033) * 1_000_000),
            )
            for i in range(10)
        ]
        report = compute_report(samples, duration_s=10 * 0.033, target_fps=30.0)
        self.assertAlmostEqual(report.e2e_latency_ms, 30.0, delta=2.0)
        self.assertTrue(report.e2e_latency_ok)


# ---------------------------------------------------------------------------
# compute_report — fail scenarios
# ---------------------------------------------------------------------------


class TestComputeReportFail(unittest.TestCase):
    def test_fps_fail_when_too_low(self):
        """Only 15 frames in 1 s at a 30 fps target → FPS FAIL (50 % deficit)."""
        samples = _perfect_samples(n=15)
        report = compute_report(samples, duration_s=1.0, target_fps=30.0)
        self.assertFalse(report.fps_ok)
        self.assertFalse(report.passed)

    def test_fps_fail_when_too_high(self):
        """60 frames in 1 s at a 30 fps target → FPS FAIL (100 % excess)."""
        samples = _perfect_samples(n=60, interval_s=1 / 60)
        report = compute_report(samples, duration_s=1.0, target_fps=30.0)
        self.assertFalse(report.fps_ok)

    def test_fps_ok_within_margin(self):
        """25 frames in 1 s at 30 fps is within 20 % margin → FPS PASS."""
        # 25 / 30 ≈ 0.167 deviation < 0.20 → PASS
        samples = _perfect_samples(n=25)
        report = compute_report(samples, duration_s=1.0, target_fps=30.0)
        self.assertTrue(report.fps_ok)

    def test_frame_loss_fail_when_gaps_large(self):
        """Frame IDs 0,1,2,10,11,12 → 6 received in span of 13 → 54% loss."""
        ids = [0, 1, 2, 10, 11, 12]
        samples = [_make_sample(frame_id=i) for i in ids]
        report = compute_report(samples, duration_s=1.0, target_fps=30.0)
        self.assertGreater(report.frame_loss_pct, TARGET_FRAME_LOSS_PCT)
        self.assertFalse(report.frame_loss_ok)

    def test_frame_loss_zero_when_no_gaps(self):
        samples = _perfect_samples(n=30)
        report = compute_report(samples, duration_s=1.0, target_fps=30.0)
        self.assertAlmostEqual(report.frame_loss_pct, 0.0, places=2)
        self.assertTrue(report.frame_loss_ok)

    def test_latency_fail_when_assembly_too_slow(self):
        """Assembly time 200 ms > TARGET_E2E_LATENCY_MS (100 ms) → FAIL."""
        samples = _perfect_samples(n=10, assembly_s=0.200)
        report = compute_report(samples, duration_s=10 / 30, target_fps=30.0)
        self.assertFalse(report.e2e_latency_ok)
        self.assertFalse(report.passed)

    def test_jitter_fail_when_high_variance(self):
        """Alternating 10 ms / 100 ms intervals → high jitter → FAIL."""
        samples = []
        t = 1.0
        for i in range(20):
            gap = 0.010 if i % 2 == 0 else 0.100
            samples.append(
                _make_sample(
                    frame_id=i,
                    first_mono=t,
                    last_mono=t + 0.005,
                    first_wall=1_700_000_000.0 + t,
                    last_wall=1_700_000_000.0 + t + 0.005,
                )
            )
            t += gap
        report = compute_report(samples, duration_s=t, target_fps=30.0)
        self.assertGreater(report.jitter_ms, TARGET_JITTER_MS)
        self.assertFalse(report.jitter_ok)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestComputeReportEdgeCases(unittest.TestCase):
    def test_empty_samples(self):
        report = compute_report([], duration_s=1.0, target_fps=30.0)
        self.assertEqual(report.frames_received, 0)
        self.assertAlmostEqual(report.actual_fps, 0.0)
        self.assertAlmostEqual(report.frame_loss_pct, 100.0)
        self.assertFalse(report.passed)

    def test_single_sample(self):
        report = compute_report(
            [_make_sample()], duration_s=1.0, target_fps=30.0
        )
        self.assertEqual(report.frames_received, 1)
        self.assertAlmostEqual(report.jitter_ms, 0.0)

    def test_zero_duration_does_not_divide_by_zero(self):
        """Graceful handling of effectively zero duration."""
        report = compute_report([], duration_s=0.0001, target_fps=30.0)
        # actual_fps = 0 / 0.0001 = 0.0 — should not raise
        self.assertAlmostEqual(report.actual_fps, 0.0)


# ---------------------------------------------------------------------------
# _compute_frame_loss_pct
# ---------------------------------------------------------------------------


class TestComputeFrameLossPct(unittest.TestCase):
    def test_no_loss(self):
        samples = [_make_sample(frame_id=i) for i in range(10)]
        self.assertAlmostEqual(_compute_frame_loss_pct(samples, 10), 0.0)

    def test_half_loss(self):
        # IDs 0,2,4,6,8 out of span 0–8 (9 slots), received 5 → loss = 4/9 ≈ 44 %
        samples = [_make_sample(frame_id=i) for i in range(0, 9, 2)]
        pct = _compute_frame_loss_pct(samples, len(samples))
        self.assertAlmostEqual(pct, 4 / 9 * 100, places=1)

    def test_empty(self):
        self.assertAlmostEqual(_compute_frame_loss_pct([], 0), 100.0)

    def test_single_sample(self):
        self.assertAlmostEqual(_compute_frame_loss_pct([_make_sample()], 1), 0.0)


# ---------------------------------------------------------------------------
# _compute_jitter_ms
# ---------------------------------------------------------------------------


class TestComputeJitterMs(unittest.TestCase):
    def test_zero_jitter_uniform_intervals(self):
        """All frames 33 ms apart → stddev = 0."""
        samples = _perfect_samples(n=10, interval_s=0.033)
        jitter = _compute_jitter_ms(samples)
        self.assertAlmostEqual(jitter, 0.0, places=3)

    def test_known_jitter_two_values(self):
        """Alternating 10 ms / 30 ms → stddev of [10, 30] = 10 ms."""
        # last_chunk_mono values: 0, 10, 40, 50, 80 (ms)
        monos = [0.000, 0.010, 0.040, 0.050, 0.080]
        samples = [
            _make_sample(frame_id=i, last_mono=t, first_mono=t - 0.001)
            for i, t in enumerate(monos)
        ]
        jitter = _compute_jitter_ms(samples)
        # intervals in ms: 10, 30, 10, 30 → mean = 20, variance = 100, stddev = 10
        self.assertAlmostEqual(jitter, 10.0, places=2)

    def test_insufficient_samples(self):
        self.assertAlmostEqual(_compute_jitter_ms([]), 0.0)
        self.assertAlmostEqual(_compute_jitter_ms([_make_sample()]), 0.0)


# ---------------------------------------------------------------------------
# ValidationReport.summary()
# ---------------------------------------------------------------------------


class TestValidationReportSummary(unittest.TestCase):
    def _make_report(self, passed: bool = True) -> ValidationReport:
        return ValidationReport(
            duration_s=10.0,
            target_fps=30.0,
            frames_received=300,
            frames_expected=300,
            actual_fps=30.0,
            fps_ok=True,
            frame_loss_pct=0.0,
            frame_loss_ok=True,
            avg_assembly_ms=5.0,
            max_assembly_ms=12.0,
            e2e_latency_ms=5.0,
            e2e_latency_ok=True,
            latency_source="assembly",
            jitter_ms=1.0,
            jitter_ok=True,
            passed=passed,
        )

    def test_summary_contains_pass(self):
        s = self._make_report(passed=True).summary()
        self.assertIn("PASS", s)
        self.assertNotIn("FAIL", s)

    def test_summary_contains_fail_when_failed(self):
        report = self._make_report(passed=False)
        report = ValidationReport(
            **{**report.__dict__, "fps_ok": False, "passed": False}
        )
        s = report.summary()
        self.assertIn("FAIL", s)

    def test_summary_contains_fps_and_latency(self):
        s = self._make_report().summary()
        self.assertIn("FPS", s)
        self.assertIn("latency", s.lower())

    def test_summary_contains_target_values(self):
        s = self._make_report().summary()
        self.assertIn(str(int(TARGET_E2E_LATENCY_MS)), s)
        self.assertIn(str(int(TARGET_FRAME_LOSS_PCT)), s)


# ---------------------------------------------------------------------------
# LanValidator packet parsing (unit-level, no real network)
# ---------------------------------------------------------------------------


class TestLanValidatorPacketParsing(unittest.TestCase):
    """Test LanValidator internal packet handlers directly, bypassing networking."""

    def _make_validator(self) -> LanValidator:
        v = LanValidator.__new__(LanValidator)
        v.server_ip = "127.0.0.1"
        v.port = 9999
        v.duration_s = 5.0
        v.target_fps = 30.0
        v.timeout_s = 1.0
        v._sock = None
        v._running = False
        v._samples = []
        v._in_flight = {}
        return v

    def _frame_start_64(
        self,
        frame_id: int,
        frame_size: int,
        chunk_count: int,
        ts_us: int | None = None,
    ) -> bytes:
        header = struct.pack("LLL", frame_id, frame_size, chunk_count)
        pkt = b"FRAME_START" + header
        if ts_us is not None:
            pkt += struct.pack("Q", ts_us)
        return pkt

    def _chunk_64(
        self, frame_id: int, chunk_index: int, payload: bytes = b"\x00" * 100
    ) -> bytes:
        return b"CHUNK" + struct.pack("LL", frame_id, chunk_index) + payload

    def test_frame_start_64_without_timestamp(self):
        v = self._make_validator()
        pkt = self._frame_start_64(frame_id=1, frame_size=1200, chunk_count=1)
        v._handle_frame_start(pkt)
        self.assertIn(1, v._in_flight)
        self.assertIsNone(v._in_flight[1].server_ts_us)

    def test_frame_start_64_with_timestamp(self):
        v = self._make_validator()
        ts = 1_700_000_000_000_000  # 1.7e15 µs
        pkt = self._frame_start_64(frame_id=5, frame_size=2400, chunk_count=2, ts_us=ts)
        v._handle_frame_start(pkt)
        self.assertIn(5, v._in_flight)
        self.assertEqual(v._in_flight[5].server_ts_us, ts)

    def test_frame_start_32bit_fallback(self):
        v = self._make_validator()
        # 32-bit FRAME_START: 11 + 3×4 = 23 bytes
        pkt = b"FRAME_START" + struct.pack("III", 7, 1200, 1)
        v._handle_frame_start(pkt)
        self.assertIn(7, v._in_flight)

    def test_frame_start_malformed_ignored(self):
        v = self._make_validator()
        pkt = b"FRAME_START" + b"\x00" * 2  # too short
        v._handle_frame_start(pkt)
        self.assertEqual(v._in_flight, {})

    def test_single_chunk_completes_frame(self):
        v = self._make_validator()
        payload = b"\xAB" * 100
        # Register frame (1 chunk, size=100)
        pkt_fs = self._frame_start_64(frame_id=3, frame_size=100, chunk_count=1)
        v._handle_frame_start(pkt_fs)
        # Send the single chunk
        pkt_chunk = self._chunk_64(frame_id=3, chunk_index=0, payload=payload)
        v._handle_chunk(pkt_chunk)
        # Frame should be complete and removed from in_flight
        self.assertNotIn(3, v._in_flight)
        self.assertEqual(len(v._samples), 1)
        self.assertEqual(v._samples[0].frame_id, 3)

    def test_duplicate_chunk_not_double_counted(self):
        v = self._make_validator()
        pkt_fs = self._frame_start_64(frame_id=10, frame_size=2400, chunk_count=2)
        v._handle_frame_start(pkt_fs)
        pkt_chunk0 = self._chunk_64(frame_id=10, chunk_index=0, payload=b"\x01" * 1200)
        v._handle_chunk(pkt_chunk0)
        # Send chunk 0 again (duplicate)
        v._handle_chunk(pkt_chunk0)
        # Only 1 unique chunk received, frame still in-flight
        self.assertIn(10, v._in_flight)
        self.assertEqual(len(v._samples), 0)

    def test_two_chunks_complete_frame(self):
        v = self._make_validator()
        pkt_fs = self._frame_start_64(frame_id=20, frame_size=2400, chunk_count=2)
        v._handle_frame_start(pkt_fs)
        v._handle_chunk(self._chunk_64(frame_id=20, chunk_index=0, payload=b"\x01" * 1200))
        v._handle_chunk(self._chunk_64(frame_id=20, chunk_index=1, payload=b"\x02" * 1200))
        self.assertNotIn(20, v._in_flight)
        self.assertEqual(len(v._samples), 1)

    def test_chunk_for_unknown_frame_ignored(self):
        v = self._make_validator()
        pkt_chunk = self._chunk_64(frame_id=999, chunk_index=0)
        v._handle_chunk(pkt_chunk)
        self.assertEqual(v._samples, [])

    def test_registered_message_ignored(self):
        v = self._make_validator()
        v._handle_packet(b"REGISTERED")
        self.assertEqual(v._samples, [])
        self.assertEqual(v._in_flight, {})

    def test_server_ts_propagated_to_sample(self):
        v = self._make_validator()
        ts = 1_700_000_050_000_000
        pkt_fs = self._frame_start_64(frame_id=42, frame_size=100, chunk_count=1, ts_us=ts)
        v._handle_frame_start(pkt_fs)
        v._handle_chunk(self._chunk_64(frame_id=42, chunk_index=0, payload=b"\xFF" * 100))
        self.assertEqual(len(v._samples), 1)
        self.assertEqual(v._samples[0].server_ts_us, ts)


# ---------------------------------------------------------------------------
# LanValidator.run() — loopback integration test
# ---------------------------------------------------------------------------


class TestLanValidatorLoopback(unittest.TestCase):
    """Spin up a minimal mock UDP streamer on localhost and run LanValidator."""

    _MOCK_PORT = 19999

    @classmethod
    def _mock_server(
        cls,
        n_frames: int = 15,
        fps: float = 30.0,
        embed_ts: bool = False,
        stop_event: threading.Event | None = None,
    ) -> None:
        """Minimal UDP server: registers one client and sends n_frames."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(3.0)
        sock.bind(("127.0.0.1", cls._MOCK_PORT))

        client_addr = None
        try:
            # Wait for registration
            while True:
                try:
                    data, addr = sock.recvfrom(64)
                except socket.timeout:
                    return
                if data.startswith(b"REGISTER_CLIENT"):
                    client_addr = addr
                    sock.sendto(b"REGISTERED", addr)
                    break

            payload = b"\x00" * 300  # minimal valid payload
            chunk_payload_size = 1200
            for frame_id in range(n_frames):
                if stop_event and stop_event.is_set():
                    break
                chunk_count = (len(payload) + chunk_payload_size - 1) // chunk_payload_size
                header = struct.pack("LLL", frame_id, len(payload), chunk_count)
                if embed_ts:
                    header += struct.pack("Q", int(time.time() * 1_000_000))
                sock.sendto(b"FRAME_START" + header, client_addr)
                for ci in range(chunk_count):
                    offset = ci * chunk_payload_size
                    chunk = payload[offset: offset + chunk_payload_size]
                    sock.sendto(
                        b"CHUNK" + struct.pack("LL", frame_id, ci) + chunk,
                        client_addr,
                    )
                time.sleep(1.0 / fps)
        except Exception:
            pass
        finally:
            sock.close()

    def test_loopback_collects_frames_and_passes(self):
        """LanValidator against a mock server should receive ~15 frames."""
        stop = threading.Event()
        server_t = threading.Thread(
            target=self._mock_server,
            kwargs={"n_frames": 15, "fps": 30.0, "stop_event": stop},
            daemon=True,
        )
        server_t.start()
        time.sleep(0.1)  # let server bind

        validator = LanValidator(
            server_ip="127.0.0.1",
            port=self._MOCK_PORT,
            duration_s=1.0,
            target_fps=30.0,
            timeout_s=2.0,
        )
        report = validator.run()
        stop.set()
        server_t.join(timeout=2.0)

        self.assertGreaterEqual(report.frames_received, 10)
        self.assertEqual(report.latency_source, "assembly")
        # Assembly should be very low on loopback
        self.assertLess(report.avg_assembly_ms, 50.0)

    def test_loopback_with_server_timestamp(self):
        """When server embeds timestamps, latency_source should be server_timestamp."""
        stop = threading.Event()
        server_t = threading.Thread(
            target=self._mock_server,
            kwargs={"n_frames": 15, "fps": 30.0, "embed_ts": True, "stop_event": stop},
            daemon=True,
        )
        server_t.start()
        time.sleep(0.1)

        validator = LanValidator(
            server_ip="127.0.0.1",
            port=self._MOCK_PORT,
            duration_s=1.0,
            target_fps=30.0,
            timeout_s=2.0,
        )
        report = validator.run()
        stop.set()
        server_t.join(timeout=2.0)

        self.assertGreater(report.frames_received, 0)
        self.assertEqual(report.latency_source, "server_timestamp")


# ---------------------------------------------------------------------------
# LanValidator._register() error handling
# ---------------------------------------------------------------------------


class TestLanValidatorRegistrationError(unittest.TestCase):
    def test_register_raises_on_timeout(self):
        """_register() should raise RuntimeError when no server responds."""
        v = LanValidator(
            server_ip="127.0.0.1",
            port=59999,  # nothing listening
            duration_s=1.0,
            target_fps=30.0,
            timeout_s=0.3,
        )
        with self.assertRaises(RuntimeError):
            v.run()


# ---------------------------------------------------------------------------
# CLI main()
# ---------------------------------------------------------------------------


class TestMainCli(unittest.TestCase):
    def test_main_returns_2_on_connection_error(self):
        """main() exits with code 2 when the server is unreachable."""
        exit_code = main(
            [
                "--server-ip",
                "127.0.0.1",
                "--port",
                "59998",
                "--duration",
                "1",
                "--target-fps",
                "30",
            ]
        )
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
