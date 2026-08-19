#!/usr/bin/env python3
"""
WAN Validation Tool for the UDP video stream.

Measures end-to-end latency, frame loss, jitter, and optional network RTT
while receiving a live video stream.  Compares results against configurable
quality thresholds and exits 0 (pass) or 1 (fail).

Usage examples
--------------
Basic run (30 s, default thresholds):

    python wan_validator.py --server-ip 192.168.1.50

Custom duration and thresholds:

    python wan_validator.py --server-ip 192.168.1.50 \\
        --duration 60 \\
        --max-p95-ms 300 \\
        --max-loss-pct 3 \\
        --min-fps 15

Dry-run WAN simulation (requires root on Linux):

    sudo python wan_validator.py --server-ip 192.168.1.50 \\
        --wan-preset typical_wan \\
        --interface eth0

JSON report only (pipe-friendly):

    python wan_validator.py --server-ip 192.168.1.50 --json-report /tmp/report.json
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from latency_metrics import (
    FrameLatencyTracker,
    LatencyStats,
    WANQualityThresholds,
    validate_latency_results,
)
from network_sim import WAN_PRESETS, NetworkSimulator, tc_available


# ---------------------------------------------------------------------------
# Network RTT measurement
# ---------------------------------------------------------------------------


def measure_udp_rtt(
    server_ip: str,
    server_port: int = 9999,
    probe_count: int = 5,
    timeout_s: float = 2.0,
) -> Optional[float]:
    """Estimate one-way latency by measuring UDP echo round-trip / 2.

    Sends ``PING`` messages to the server and expects ``REGISTERED`` or any
    reply.  Uses the ``REGISTER_CLIENT`` handshake which the server answers
    with ``REGISTERED``.

    Returns the mean RTT in milliseconds, or None if the server is
    unreachable within the timeout.
    """
    rtts = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout_s)
    try:
        for _ in range(probe_count):
            t0 = time.monotonic()
            try:
                sock.sendto(b"REGISTER_CLIENT", (server_ip, server_port))
                sock.recvfrom(1024)
                rtt = (time.monotonic() - t0) * 1000.0
                rtts.append(rtt)
                # Immediately deregister so we don't start a full stream
                sock.sendto(b"DISCONNECT", (server_ip, server_port))
            except socket.timeout:
                pass
            time.sleep(0.1)
    finally:
        sock.close()

    if not rtts:
        return None
    return sum(rtts) / len(rtts)


# ---------------------------------------------------------------------------
# Frame receiver for validation (headless – no OpenCV display)
# ---------------------------------------------------------------------------


class ValidationReceiver:
    """Minimal UDP frame receiver that feeds a FrameLatencyTracker.

    Does not display frames; only measures timing for validation purposes.
    """

    PAYLOAD_SIZE = 1200

    def __init__(
        self,
        server_ip: str,
        server_port: int = 9999,
        client_port: int = 9999,
        expected_fps: float = 30.0,
    ) -> None:
        self.server_ip = server_ip
        self.server_port = server_port
        self.client_port = client_port
        self.tracker = FrameLatencyTracker(expected_fps=expected_fps)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(2.0)
        self._sock.bind(("", self.client_port))

        self._running = False
        self._frames_received = 0
        self._decode_failures = 0

        # Chunk reassembly state
        self._pending: dict = {}
        self._expected_chunks: dict = {}
        self._received_chunks: dict = {}

    def start(self, duration_s: float) -> None:
        """Receive frames for *duration_s* seconds, then stop."""
        self._running = True
        timer = threading.Timer(duration_s, self.stop)
        timer.daemon = True
        timer.start()

        try:
            self._register()
            self._receive_loop()
        finally:
            timer.cancel()
            self._disconnect()
            self._sock.close()

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _register(self) -> None:
        self._sock.sendto(b"REGISTER_CLIENT", (self.server_ip, self.server_port))
        try:
            data, _ = self._sock.recvfrom(1024)
            if data == b"REGISTERED":
                print(f"  Registered with server {self.server_ip}:{self.server_port}")
            else:
                print(f"  Unexpected registration response: {data!r}")
        except socket.timeout:
            print("  Warning: no registration acknowledgment received")

        # Start keepalive thread
        ka_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        ka_thread.start()

    def _keepalive_loop(self) -> None:
        while self._running:
            try:
                self._sock.sendto(
                    b"KEEPALIVE", (self.server_ip, self.server_port)
                )
            except Exception:
                pass
            time.sleep(5.0)

    def _receive_loop(self) -> None:
        while self._running:
            try:
                data, _ = self._sock.recvfrom(65536)
            except socket.timeout:
                self.tracker.drop_stale_frames(max_age_s=2.0)
                continue
            except OSError:
                break

            if data == b"REGISTERED":
                continue

            if data.startswith(b"FRAME_START"):
                self._handle_frame_start(data)
            elif data.startswith(b"CHUNK"):
                self._handle_chunk(data)

    def _handle_frame_start(self, data: bytes) -> None:
        # Try 64-bit struct.pack("LLL") format (Pi default) first
        if len(data) == 35:
            try:
                frame_id, frame_size, chunk_count = struct.unpack("LLL", data[11:35])
                if frame_size > 0:
                    self._init_frame(frame_id, frame_size, chunk_count)
                    return
            except struct.error:
                pass
        # Fallback: 32-bit format
        if len(data) >= 23:
            try:
                frame_id, frame_size, chunk_count = struct.unpack("III", data[11:23])
                if frame_size > 0:
                    self._init_frame(frame_id, frame_size, chunk_count)
            except struct.error:
                pass

    def _init_frame(self, frame_id: int, frame_size: int, chunk_count: int) -> None:
        self._pending[frame_id] = bytearray(frame_size)
        self._expected_chunks[frame_id] = chunk_count
        self._received_chunks[frame_id] = set()
        self.tracker.record_first_chunk(frame_id, chunk_count, frame_size)

    def _handle_chunk(self, data: bytes) -> None:
        # Try 64-bit header ("CHUNK" + 2×uint64 = 5 + 16 = 21 bytes prefix)
        if len(data) >= 21:
            try:
                frame_id, chunk_index = struct.unpack("LL", data[5:21])
                payload = data[21:]
                if self._store_chunk(frame_id, chunk_index, payload):
                    return
            except struct.error:
                pass
        # Fallback: 32-bit header ("CHUNK" + 2×uint32 = 5 + 8 = 13 bytes prefix)
        if len(data) >= 13:
            try:
                frame_id, chunk_index = struct.unpack("II", data[5:13])
                payload = data[13:]
                self._store_chunk(frame_id, chunk_index, payload)
            except struct.error:
                pass

    def _store_chunk(
        self, frame_id: int, chunk_index: int, payload: bytes
    ) -> bool:
        if frame_id not in self._pending:
            return False
        if chunk_index in self._received_chunks[frame_id]:
            return True  # Duplicate

        offset = chunk_index * self.PAYLOAD_SIZE
        buf = self._pending[frame_id]
        if offset < len(buf):
            end = min(offset + len(payload), len(buf))
            buf[offset:end] = payload[: end - offset]
            self._received_chunks[frame_id].add(chunk_index)

        if len(self._received_chunks[frame_id]) >= self._expected_chunks[frame_id]:
            self._pending.pop(frame_id, None)
            self._expected_chunks.pop(frame_id, None)
            self._received_chunks.pop(frame_id, None)
            self.tracker.record_complete(frame_id)
            self._frames_received += 1

        return True

    def _disconnect(self) -> None:
        try:
            self._sock.sendto(b"DISCONNECT", (self.server_ip, self.server_port))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate UDP video stream latency over WAN conditions",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--server-ip", required=True, help="Streaming server IP")
    parser.add_argument(
        "--server-port", type=int, default=9999, help="Streaming server port"
    )
    parser.add_argument(
        "--client-port", type=int, default=9999, help="Local UDP bind port"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="Measurement window in seconds",
    )
    parser.add_argument(
        "--expected-fps",
        type=float,
        default=30.0,
        help="Expected source FPS (used for loss estimate)",
    )
    parser.add_argument(
        "--max-p95-ms",
        type=float,
        default=200.0,
        help="Max allowed p95 frame-assembly latency (ms)",
    )
    parser.add_argument(
        "--max-loss-pct",
        type=float,
        default=5.0,
        help="Max allowed frame loss percentage",
    )
    parser.add_argument(
        "--min-fps",
        type=float,
        default=20.0,
        help="Minimum accepted mean FPS at receiver",
    )
    parser.add_argument(
        "--max-jitter-ms",
        type=float,
        default=50.0,
        help="Max allowed mean inter-frame jitter (ms)",
    )
    parser.add_argument(
        "--wan-preset",
        choices=sorted(WAN_PRESETS.keys()),
        default=None,
        help=(
            "Apply a WAN simulation preset using tc netem "
            "(requires root; Linux only)"
        ),
    )
    parser.add_argument(
        "--interface",
        default="eth0",
        help="Network interface for tc netem simulation",
    )
    parser.add_argument(
        "--dry-run-sim",
        action="store_true",
        help="Print tc commands instead of executing them",
    )
    parser.add_argument(
        "--skip-rtt",
        action="store_true",
        help="Skip the initial RTT measurement",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        default=None,
        help="Write JSON report to this path",
    )
    return parser


def print_stats(stats: LatencyStats) -> None:
    print("\n─────────────────────────────────────")
    print("  Latency & Quality Metrics")
    print("─────────────────────────────────────")
    print(f"  Frames received:        {stats.sample_count}")
    print(f"  Duration:               {stats.duration_s:.1f} s")
    print(f"  Mean FPS:               {stats.mean_fps:.1f}")
    print(f"  Frame loss:             {stats.frame_loss_pct:.1f} %")
    print(f"  Assembly latency p50:   {stats.median_assembly_ms:.1f} ms")
    print(f"  Assembly latency p95:   {stats.p95_assembly_ms:.1f} ms")
    print(f"  Assembly latency p99:   {stats.p99_assembly_ms:.1f} ms")
    print(f"  Max assembly latency:   {stats.max_assembly_ms:.1f} ms")
    print(f"  Mean jitter:            {stats.mean_jitter_ms:.1f} ms")
    if stats.rtt_ms is not None:
        print(f"  Network RTT:            {stats.rtt_ms:.1f} ms")
    print("─────────────────────────────────────\n")


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    thresholds = WANQualityThresholds(
        max_assembly_ms_p95=args.max_p95_ms,
        max_frame_loss_pct=args.max_loss_pct,
        min_fps=args.min_fps,
        max_jitter_ms=args.max_jitter_ms,
    )

    # ── Optional network simulation ────────────────────────────────────────
    sim: Optional[NetworkSimulator] = None
    active_preset = None
    if args.wan_preset:
        preset = WAN_PRESETS[args.wan_preset]
        if not tc_available() and not args.dry_run_sim:
            print(
                f"Warning: 'tc' not found in PATH; cannot apply preset "
                f"'{args.wan_preset}'. Re-run with --dry-run-sim to preview commands."
            )
        else:
            sim = NetworkSimulator(
                interface=args.interface, dry_run=args.dry_run_sim
            )
            print(
                f"Applying WAN preset '{preset.name}': {preset.description}\n"
                f"  latency={preset.latency_ms} ms  jitter={preset.jitter_ms} ms  "
                f"loss={preset.loss_pct}%  bw={preset.bandwidth_kbps} kbps"
            )
            sim.apply(preset)
            active_preset = preset

    try:
        # ── RTT measurement ────────────────────────────────────────────────
        rtt_ms: Optional[float] = None
        if not args.skip_rtt:
            print(
                f"Measuring RTT to {args.server_ip}:{args.server_port} …",
                end="",
                flush=True,
            )
            rtt_ms = measure_udp_rtt(args.server_ip, args.server_port)
            if rtt_ms is not None:
                print(f" {rtt_ms:.1f} ms")
            else:
                print(" unreachable (skipping RTT)")

        # ── Frame receive session ──────────────────────────────────────────
        print(
            f"\nReceiving frames from {args.server_ip}:{args.server_port} "
            f"for {args.duration:.0f} s …"
        )
        receiver = ValidationReceiver(
            server_ip=args.server_ip,
            server_port=args.server_port,
            client_port=args.client_port,
            expected_fps=args.expected_fps,
        )
        receiver.start(duration_s=args.duration)

        # ── Compute and print stats ───────────────────────────────────────
        stats = receiver.tracker.compute_stats(rtt_ms=rtt_ms)
        print_stats(stats)

        # ── Validate ──────────────────────────────────────────────────────
        result = validate_latency_results(stats, thresholds)
        preset_label = f" [{active_preset.name}]" if active_preset else ""
        if result.passed:
            print(f"RESULT: PASS{preset_label}")
        else:
            print(f"RESULT: FAIL{preset_label}")
            for failure in result.failures:
                print(f"  ✗ {failure}")

        # ── JSON report ───────────────────────────────────────────────────
        report = {
            "server": f"{args.server_ip}:{args.server_port}",
            "wan_preset": args.wan_preset,
            "thresholds": {
                "max_assembly_ms_p95": thresholds.max_assembly_ms_p95,
                "max_frame_loss_pct": thresholds.max_frame_loss_pct,
                "min_fps": thresholds.min_fps,
                "max_jitter_ms": thresholds.max_jitter_ms,
            },
            "stats": stats.to_dict(),
            "validation": result.to_dict(),
        }
        if args.json_report:
            args.json_report.write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(f"Report written to {args.json_report}")

        return 0 if result.passed else 1

    finally:
        if sim is not None:
            sim.clear()


if __name__ == "__main__":
    sys.exit(main())
