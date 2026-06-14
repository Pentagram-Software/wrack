"""LAN latency and quality validation for the UDP video streaming pipeline.

Connects to a running :class:`~edge.video_streamer.UDPVideoStreamer`, receives
frames for a configurable duration, and produces a :class:`ValidationReport`
comparing measured values against PRD targets.

Pass/fail targets (aligned with PRD §NFR and streamer README):
  - E2E latency     < 100 ms   (UDP path on LAN)
  - FPS             within 20 % of target
  - Frame loss      < 5 %
  - Jitter (stddev) < 20 ms

Usage (standalone)::

    python3 lan_validate.py --server-ip 192.168.1.50 --duration 10 --target-fps 30
    # Exit code 0 = all targets met; 1 = one or more targets missed; 2 = error

Timestamp-aware mode (requires ``--embed-timestamps`` on the server)::

    # Server: python3 streamer.py --embed-timestamps
    # Client: python3 lan_validate.py --server-ip 192.168.1.50
"""

from __future__ import annotations

import argparse
import math
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------------
# Validation targets
# ---------------------------------------------------------------------------

TARGET_E2E_LATENCY_MS: float = 100.0
"""Maximum acceptable E2E latency in milliseconds (UDP path on LAN)."""

TARGET_FPS_MARGIN: float = 0.20
"""Acceptable fractional deviation from the target frame-rate (20 %)."""

TARGET_FRAME_LOSS_PCT: float = 5.0
"""Maximum acceptable frame-loss percentage."""

TARGET_JITTER_MS: float = 20.0
"""Maximum acceptable inter-frame jitter (standard deviation) in milliseconds."""

# ---------------------------------------------------------------------------
# Protocol constants (mirror shared/video-protocol spec)
# ---------------------------------------------------------------------------

_FRAME_START_MARKER = b"FRAME_START"  # 11 bytes
_CHUNK_MARKER = b"CHUNK"              # 5 bytes

# FRAME_START packet lengths (64-bit L format used by Pi)
_FS_LEN_64 = 11 + 3 * 8         # 35 — frame_id, frame_size, chunk_count
_FS_LEN_64_TS = _FS_LEN_64 + 8  # 43 — + uint64 capture timestamp
# Fallback 32-bit format (non-Pi platforms)
_FS_LEN_32 = 11 + 3 * 4         # 23

# CHUNK header lengths
_CHUNK_HDR_64 = 5 + 2 * 8       # 21  ("CHUNK" + frame_id:u64 + chunk_index:u64)
_CHUNK_HDR_32 = 5 + 2 * 4       # 13  ("CHUNK" + frame_id:u32 + chunk_index:u32)

_CHUNK_PAYLOAD_SIZE = 1200       # bytes, matches streamer default


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class _FrameState:
    """Mutable reassembly buffer for a single in-flight frame."""

    frame_id: int
    frame_size: int
    chunk_count: int
    buf: bytearray
    received_indices: set
    first_chunk_wall: float    # time.time() when first chunk arrived
    first_chunk_mono: float    # time.monotonic() when first chunk arrived
    server_ts_us: Optional[int] = None


@dataclass
class FrameSample:
    """Immutable timing record for a completed frame."""

    frame_id: int
    first_chunk_wall: float
    last_chunk_wall: float
    first_chunk_mono: float
    last_chunk_mono: float
    server_ts_us: Optional[int] = None


@dataclass
class ValidationReport:
    """Results of a :class:`LanValidator` run."""

    duration_s: float
    target_fps: float

    frames_received: int
    frames_expected: int

    actual_fps: float
    fps_ok: bool

    frame_loss_pct: float
    frame_loss_ok: bool

    avg_assembly_ms: float
    max_assembly_ms: float

    e2e_latency_ms: float
    e2e_latency_ok: bool
    latency_source: str   # "server_timestamp" | "assembly"

    jitter_ms: float
    jitter_ok: bool

    passed: bool

    def summary(self) -> str:
        """Return a human-readable multi-line validation report."""
        sep = "=" * 58
        lines = [
            sep,
            "  LAN Validation Report",
            sep,
            f"  Duration          : {self.duration_s:.1f}s",
            f"  Target FPS        : {self.target_fps}",
            f"  Frames received   : {self.frames_received}  (expected ~{self.frames_expected})",
            "",
            (
                f"  FPS               : {self.actual_fps:.1f}  "
                f"{'PASS' if self.fps_ok else 'FAIL'}  "
                f"(target ±{TARGET_FPS_MARGIN*100:.0f}%)"
            ),
            (
                f"  Frame loss        : {self.frame_loss_pct:.1f}%  "
                f"{'PASS' if self.frame_loss_ok else 'FAIL'}  "
                f"(target <{TARGET_FRAME_LOSS_PCT}%)"
            ),
            (
                f"  E2E latency       : {self.e2e_latency_ms:.1f}ms  "
                f"{'PASS' if self.e2e_latency_ok else 'FAIL'}  "
                f"(target <{TARGET_E2E_LATENCY_MS}ms)  [{self.latency_source}]"
            ),
            (
                f"  Jitter (stddev)   : {self.jitter_ms:.1f}ms  "
                f"{'PASS' if self.jitter_ok else 'FAIL'}  "
                f"(target <{TARGET_JITTER_MS}ms)"
            ),
            f"  Avg assembly      : {self.avg_assembly_ms:.1f}ms",
            f"  Max assembly      : {self.max_assembly_ms:.1f}ms",
            "",
            f"  Overall           : {'PASS' if self.passed else 'FAIL'}",
            sep,
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report computation (pure function — easily unit-tested)
# ---------------------------------------------------------------------------


def compute_report(
    samples: List[FrameSample],
    duration_s: float,
    target_fps: float,
) -> ValidationReport:
    """Compute a :class:`ValidationReport` from a list of completed frame samples.

    This is a pure function with no I/O, suitable for direct unit testing.

    :param samples: Frame timing records collected during the validation run.
    :param duration_s: Elapsed wall-clock seconds of the run.
    :param target_fps: Configured server frame-rate target.
    :returns: Populated :class:`ValidationReport`.
    """
    frames_received = len(samples)
    frames_expected = max(1, int(round(duration_s * target_fps)))

    actual_fps = frames_received / duration_s if duration_s > 0 else 0.0
    fps_ok = abs(actual_fps - target_fps) / max(target_fps, 1e-9) <= TARGET_FPS_MARGIN

    # Frame-loss via frame_id gap analysis
    frame_loss_pct = _compute_frame_loss_pct(samples, frames_received)
    frame_loss_ok = frame_loss_pct < TARGET_FRAME_LOSS_PCT

    # Assembly latency (in-receiver: first chunk → frame complete)
    assembly_ms_list = [
        (s.last_chunk_mono - s.first_chunk_mono) * 1_000.0 for s in samples
    ]
    avg_assembly_ms = (
        sum(assembly_ms_list) / len(assembly_ms_list) if assembly_ms_list else 0.0
    )
    max_assembly_ms = max(assembly_ms_list) if assembly_ms_list else 0.0

    # E2E latency — prefer server timestamps, fall back to assembly time
    ts_samples = [s for s in samples if s.server_ts_us is not None]
    if ts_samples:
        # Compute receive_wall_time - server_capture_time for each frame.
        # Uses last_chunk_wall (wall-clock time when frame was complete) minus
        # the server capture timestamp converted to seconds.
        # Assumes NTP clock sync (typically ≤ 5 ms on a home LAN).
        e2e_ms_list = [
            (s.last_chunk_wall - s.server_ts_us / 1_000_000.0) * 1_000.0
            for s in ts_samples
        ]
        # Negative values indicate clock skew; use absolute value for reporting
        e2e_latency_ms = sum(abs(v) for v in e2e_ms_list) / len(e2e_ms_list)
        latency_source = "server_timestamp"
    else:
        e2e_latency_ms = avg_assembly_ms
        latency_source = "assembly"

    e2e_latency_ok = e2e_latency_ms < TARGET_E2E_LATENCY_MS

    # Jitter — standard deviation of inter-frame completion intervals
    jitter_ms = _compute_jitter_ms(samples)
    jitter_ok = jitter_ms < TARGET_JITTER_MS

    passed = fps_ok and frame_loss_ok and e2e_latency_ok and jitter_ok

    return ValidationReport(
        duration_s=duration_s,
        target_fps=target_fps,
        frames_received=frames_received,
        frames_expected=frames_expected,
        actual_fps=actual_fps,
        fps_ok=fps_ok,
        frame_loss_pct=frame_loss_pct,
        frame_loss_ok=frame_loss_ok,
        avg_assembly_ms=avg_assembly_ms,
        max_assembly_ms=max_assembly_ms,
        e2e_latency_ms=e2e_latency_ms,
        e2e_latency_ok=e2e_latency_ok,
        latency_source=latency_source,
        jitter_ms=jitter_ms,
        jitter_ok=jitter_ok,
        passed=passed,
    )


def _compute_frame_loss_pct(
    samples: List[FrameSample], frames_received: int
) -> float:
    """Estimate frame loss % using frame_id gap analysis."""
    if not samples:
        return 100.0
    sorted_ids = sorted(s.frame_id for s in samples)
    if len(sorted_ids) < 2:
        return 0.0
    id_span = sorted_ids[-1] - sorted_ids[0] + 1
    if id_span <= 0:
        return 0.0
    lost = id_span - frames_received
    return max(0.0, lost / id_span * 100.0)


def _compute_jitter_ms(samples: List[FrameSample]) -> float:
    """Compute standard deviation of inter-frame completion intervals in ms."""
    if len(samples) < 2:
        return 0.0
    sorted_samples = sorted(samples, key=lambda s: s.last_chunk_mono)
    intervals = [
        (sorted_samples[i].last_chunk_mono - sorted_samples[i - 1].last_chunk_mono) * 1_000.0
        for i in range(1, len(sorted_samples))
    ]
    mean = sum(intervals) / len(intervals)
    variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
    return math.sqrt(variance)


# ---------------------------------------------------------------------------
# LanValidator — live UDP connection + sample collection
# ---------------------------------------------------------------------------


class LanValidator:
    """Connect to a UDP video server, collect frame samples, compute a report.

    Example::

        validator = LanValidator("192.168.1.50", port=9999, duration_s=10, target_fps=30)
        report = validator.run()
        print(report.summary())
        sys.exit(0 if report.passed else 1)

    :param server_ip: IP address of the running :class:`UDPVideoStreamer`.
    :param port: UDP port of the streamer (default 9999).
    :param duration_s: How many seconds to collect samples.
    :param target_fps: Expected server frame-rate (used for pass/fail FPS check).
    :param timeout_s: Socket receive timeout; also controls keepalive interval.
    """

    def __init__(
        self,
        server_ip: str,
        port: int = 9999,
        duration_s: float = 10.0,
        target_fps: float = 30.0,
        timeout_s: float = 3.0,
    ) -> None:
        self.server_ip = server_ip
        self.port = port
        self.duration_s = duration_s
        self.target_fps = target_fps
        self.timeout_s = timeout_s

        self._sock: Optional[socket.socket] = None
        self._running = False
        self._samples: List[FrameSample] = []
        self._in_flight: dict = {}  # frame_id → _FrameState

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> ValidationReport:
        """Run the validation, return a :class:`ValidationReport`.

        Connects, collects frames for ``duration_s``, disconnects, computes
        and returns the report.

        :raises RuntimeError: if registration with the server fails.
        """
        self._setup_socket()
        try:
            self._register()
            keepalive_t = threading.Thread(target=self._keepalive_loop, daemon=True)
            keepalive_t.start()
            deadline = time.monotonic() + self.duration_s
            start_wall = time.time()
            self._running = True
            self._receive_loop(deadline)
            elapsed = time.time() - start_wall
        finally:
            self._running = False
            self._disconnect()
            if self._sock:
                self._sock.close()
                self._sock = None

        return compute_report(self._samples, elapsed, self.target_fps)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _setup_socket(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(self.timeout_s)
        sock.bind(("", 0))
        self._sock = sock

    def _register(self) -> None:
        assert self._sock is not None
        self._sock.sendto(b"REGISTER_CLIENT", (self.server_ip, self.port))
        try:
            data, _ = self._sock.recvfrom(64)
            if data != b"REGISTERED":
                raise RuntimeError(
                    f"Unexpected registration response: {data!r}"
                )
        except socket.timeout as exc:
            raise RuntimeError(
                f"No response from {self.server_ip}:{self.port} — "
                "is the streamer running?"
            ) from exc

    def _keepalive_loop(self) -> None:
        while self._running:
            try:
                if self._sock:
                    self._sock.sendto(b"KEEPALIVE", (self.server_ip, self.port))
            except Exception:
                pass
            time.sleep(5.0)

    def _disconnect(self) -> None:
        try:
            if self._sock:
                self._sock.sendto(b"DISCONNECT", (self.server_ip, self.port))
        except Exception:
            pass

    def _receive_loop(self, deadline: float) -> None:
        assert self._sock is not None
        while time.monotonic() < deadline:
            try:
                data, _ = self._sock.recvfrom(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            self._handle_packet(data)

    def _handle_packet(self, data: bytes) -> None:
        if data == b"REGISTERED":
            return
        if data.startswith(_FRAME_START_MARKER):
            self._handle_frame_start(data)
        elif data.startswith(_CHUNK_MARKER):
            self._handle_chunk(data)

    def _handle_frame_start(self, data: bytes) -> None:
        now_wall = time.time()
        now_mono = time.monotonic()
        n = len(data)

        server_ts_us: Optional[int] = None

        if n == _FS_LEN_64_TS:
            # 64-bit + timestamp
            frame_id, frame_size, chunk_count = struct.unpack_from("LLL", data, 11)
            server_ts_us = struct.unpack_from("Q", data, _FS_LEN_64)[0]
        elif n == _FS_LEN_64:
            frame_id, frame_size, chunk_count = struct.unpack_from("LLL", data, 11)
        elif n >= _FS_LEN_32:
            frame_id, frame_size, chunk_count = struct.unpack_from("III", data, 11)
        else:
            return  # malformed

        if frame_size == 0 or chunk_count == 0:
            return

        self._in_flight[frame_id] = _FrameState(
            frame_id=frame_id,
            frame_size=frame_size,
            chunk_count=chunk_count,
            buf=bytearray(frame_size),
            received_indices=set(),
            first_chunk_wall=now_wall,
            first_chunk_mono=now_mono,
            server_ts_us=server_ts_us,
        )

    def _handle_chunk(self, data: bytes) -> None:
        now_wall = time.time()
        now_mono = time.monotonic()
        n = len(data)

        if n >= _CHUNK_HDR_64:
            try:
                frame_id, chunk_index = struct.unpack_from("LL", data, 5)
                payload = data[_CHUNK_HDR_64:]
            except struct.error:
                return
        elif n >= _CHUNK_HDR_32:
            try:
                frame_id, chunk_index = struct.unpack_from("II", data, 5)
                payload = data[_CHUNK_HDR_32:]
            except struct.error:
                return
        else:
            return

        state = self._in_flight.get(frame_id)
        if state is None:
            return

        if chunk_index not in state.received_indices:
            offset = chunk_index * _CHUNK_PAYLOAD_SIZE
            end = min(offset + len(payload), len(state.buf))
            if offset < len(state.buf):
                state.buf[offset:end] = payload[: end - offset]
            state.received_indices.add(chunk_index)

        if len(state.received_indices) >= state.chunk_count:
            # Frame complete
            sample = FrameSample(
                frame_id=state.frame_id,
                first_chunk_wall=state.first_chunk_wall,
                last_chunk_wall=now_wall,
                first_chunk_mono=state.first_chunk_mono,
                last_chunk_mono=now_mono,
                server_ts_us=state.server_ts_us,
            )
            self._samples.append(sample)
            del self._in_flight[frame_id]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate LAN video stream latency and quality against PRD targets.\n\n"
            "Targets:\n"
            f"  E2E latency  < {TARGET_E2E_LATENCY_MS:.0f} ms\n"
            f"  FPS          within {TARGET_FPS_MARGIN*100:.0f}% of target\n"
            f"  Frame loss   < {TARGET_FRAME_LOSS_PCT:.0f}%\n"
            f"  Jitter       < {TARGET_JITTER_MS:.0f} ms (stddev of inter-frame intervals)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--server-ip",
        required=True,
        help="IP address of the running UDPVideoStreamer",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9999,
        help="UDP port of the streamer (default: 9999)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Seconds to collect samples (default: 10)",
    )
    parser.add_argument(
        "--target-fps",
        type=float,
        default=30.0,
        help="Expected server frame rate (default: 30)",
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    """CLI entry-point.

    :returns: 0 = all targets met; 1 = one or more targets missed; 2 = error.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    print(
        f"Connecting to {args.server_ip}:{args.port} "
        f"for {args.duration:.0f}s (target {args.target_fps:.0f} fps)..."
    )

    try:
        validator = LanValidator(
            server_ip=args.server_ip,
            port=args.port,
            duration_s=args.duration,
            target_fps=args.target_fps,
        )
        report = validator.run()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 2

    print(report.summary())
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
