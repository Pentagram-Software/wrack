"""
Latency measurement primitives for WAN validation of the UDP video stream.

This module provides:
- FrameTimingRecord  – per-frame timing snapshot
- LatencyStats       – statistical summary over a sample set
- FrameLatencyTracker – accumulates per-frame timing from the receiver loop
- WANQualityThresholds – configurable pass/fail thresholds
- validate_latency_results – compare a LatencyStats report against thresholds
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FrameTimingRecord:
    """Timing snapshot for a single received frame.

    Attributes:
        frame_id:         Monotonic frame counter from the streamer.
        first_chunk_ts:   Wall-clock timestamp (seconds) when the first chunk
                          of this frame was received.
        complete_ts:      Wall-clock timestamp when the last chunk arrived and
                          the frame was fully reassembled.
        chunk_count:      Number of UDP chunks that carried this frame.
        byte_size:        Total payload bytes in the reassembled frame.
    """

    frame_id: int
    first_chunk_ts: float
    complete_ts: float
    chunk_count: int
    byte_size: int

    @property
    def assembly_latency_ms(self) -> float:
        """Time (ms) from first chunk received to full frame reassembled."""
        return (self.complete_ts - self.first_chunk_ts) * 1000.0


@dataclass
class LatencyStats:
    """Statistical summary of latency and quality metrics over a run.

    All latency values are in milliseconds unless noted.
    """

    sample_count: int = 0
    duration_s: float = 0.0
    mean_assembly_ms: float = 0.0
    median_assembly_ms: float = 0.0
    p95_assembly_ms: float = 0.0
    p99_assembly_ms: float = 0.0
    max_assembly_ms: float = 0.0
    mean_fps: float = 0.0
    frame_loss_pct: float = 0.0
    mean_jitter_ms: float = 0.0
    rtt_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "sample_count": self.sample_count,
            "duration_s": round(self.duration_s, 3),
            "mean_assembly_ms": round(self.mean_assembly_ms, 2),
            "median_assembly_ms": round(self.median_assembly_ms, 2),
            "p95_assembly_ms": round(self.p95_assembly_ms, 2),
            "p99_assembly_ms": round(self.p99_assembly_ms, 2),
            "max_assembly_ms": round(self.max_assembly_ms, 2),
            "mean_fps": round(self.mean_fps, 2),
            "frame_loss_pct": round(self.frame_loss_pct, 2),
            "mean_jitter_ms": round(self.mean_jitter_ms, 2),
            "rtt_ms": round(self.rtt_ms, 2) if self.rtt_ms is not None else None,
        }


@dataclass
class WANQualityThresholds:
    """Pass/fail thresholds for WAN playback validation.

    Defaults are derived from the PRD non-functional requirements:
    - UDP stream targets <500 ms E2E latency (LL-HLS / WebRTC reference).
    - Frame loss below 5 % is acceptable on a WAN path.
    - Mean FPS should stay ≥80 % of the configured source FPS.

    Attributes:
        max_assembly_ms_p95:  Maximum allowed p95 frame-assembly latency (ms).
        max_frame_loss_pct:   Maximum allowed frame-loss percentage.
        min_fps:              Minimum acceptable received frame rate.
        max_jitter_ms:        Maximum allowed mean inter-frame jitter (ms).
    """

    max_assembly_ms_p95: float = 200.0
    max_frame_loss_pct: float = 5.0
    min_fps: float = 20.0
    max_jitter_ms: float = 50.0


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class FrameLatencyTracker:
    """Accumulates per-frame timing records during a receiver session.

    Usage::

        tracker = FrameLatencyTracker()
        tracker.record_first_chunk(frame_id, chunk_count, byte_size)
        ...
        tracker.record_complete(frame_id)
        stats = tracker.compute_stats()
    """

    def __init__(self, expected_fps: float = 30.0) -> None:
        self._expected_fps = expected_fps
        self._pending: Dict[int, Dict] = {}
        self._records: List[FrameTimingRecord] = []
        self._session_start: Optional[float] = None
        self._max_seen_frame_id: int = -1

    def record_first_chunk(
        self, frame_id: int, chunk_count: int, byte_size: int
    ) -> None:
        """Call when FRAME_START arrives for *frame_id*."""
        if self._session_start is None:
            self._session_start = time.monotonic()
        now = time.monotonic()
        self._pending[frame_id] = {
            "first_ts": now,
            "chunk_count": chunk_count,
            "byte_size": byte_size,
        }
        if frame_id > self._max_seen_frame_id:
            self._max_seen_frame_id = frame_id

    def record_complete(self, frame_id: int) -> Optional[FrameTimingRecord]:
        """Call when all chunks for *frame_id* have been reassembled.

        Returns the FrameTimingRecord if the frame was tracked, else None.
        """
        entry = self._pending.pop(frame_id, None)
        if entry is None:
            return None
        record = FrameTimingRecord(
            frame_id=frame_id,
            first_chunk_ts=entry["first_ts"],
            complete_ts=time.monotonic(),
            chunk_count=entry["chunk_count"],
            byte_size=entry["byte_size"],
        )
        self._records.append(record)
        return record

    def drop_stale_frames(self, max_age_s: float = 2.0) -> int:
        """Remove incomplete frame entries older than *max_age_s* seconds.

        Returns the number of frames dropped (counted as lost).
        """
        now = time.monotonic()
        stale = [
            fid
            for fid, entry in self._pending.items()
            if now - entry["first_ts"] > max_age_s
        ]
        for fid in stale:
            del self._pending[fid]
        return len(stale)

    @property
    def completed_count(self) -> int:
        return len(self._records)

    def compute_stats(self, rtt_ms: Optional[float] = None) -> LatencyStats:
        """Compute summary statistics over all completed frames.

        Args:
            rtt_ms: Optional measured network round-trip time in milliseconds.

        Returns:
            LatencyStats populated with computed metrics.
        """
        records = self._records
        if not records:
            return LatencyStats(rtt_ms=rtt_ms)

        now = time.monotonic()
        session_start = self._session_start or records[0].first_chunk_ts
        duration_s = now - session_start

        # Assembly latency list
        latencies = [r.assembly_latency_ms for r in records]
        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)

        mean_assembly = sum(latencies) / n
        median_assembly = _percentile(latencies_sorted, 50)
        p95 = _percentile(latencies_sorted, 95)
        p99 = _percentile(latencies_sorted, 99)
        max_assembly = latencies_sorted[-1]

        # FPS
        mean_fps = n / duration_s if duration_s > 0 else 0.0

        # Frame loss estimate: compare completed frames vs expected from time
        expected_frames = max(1, duration_s * self._expected_fps)
        frame_loss_pct = max(0.0, (1.0 - n / expected_frames) * 100.0)

        # Jitter: mean absolute deviation of inter-completion times
        completion_times = sorted(r.complete_ts for r in records)
        jitter_ms = _compute_jitter_ms(completion_times)

        return LatencyStats(
            sample_count=n,
            duration_s=duration_s,
            mean_assembly_ms=mean_assembly,
            median_assembly_ms=median_assembly,
            p95_assembly_ms=p95,
            p99_assembly_ms=p99,
            max_assembly_ms=max_assembly,
            mean_fps=mean_fps,
            frame_loss_pct=frame_loss_pct,
            mean_jitter_ms=jitter_ms,
            rtt_ms=rtt_ms,
        )

    def reset(self) -> None:
        """Clear all accumulated data."""
        self._pending.clear()
        self._records.clear()
        self._session_start = None
        self._max_seen_frame_id = -1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Outcome of comparing LatencyStats against WANQualityThresholds."""

    passed: bool
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "failures": self.failures}


def validate_latency_results(
    stats: LatencyStats,
    thresholds: Optional[WANQualityThresholds] = None,
) -> ValidationResult:
    """Check *stats* against *thresholds* and return a ValidationResult.

    Args:
        stats:      Computed LatencyStats from a receiver session.
        thresholds: Quality thresholds; defaults to WANQualityThresholds().

    Returns:
        ValidationResult with passed=True when all checks pass.
    """
    if thresholds is None:
        thresholds = WANQualityThresholds()

    if stats.sample_count == 0:
        return ValidationResult(
            passed=False, failures=["No frames received – cannot validate"]
        )

    failures: List[str] = []

    if stats.p95_assembly_ms > thresholds.max_assembly_ms_p95:
        failures.append(
            f"p95 assembly latency {stats.p95_assembly_ms:.1f} ms "
            f"exceeds limit {thresholds.max_assembly_ms_p95:.1f} ms"
        )

    if stats.frame_loss_pct > thresholds.max_frame_loss_pct:
        failures.append(
            f"Frame loss {stats.frame_loss_pct:.1f}% "
            f"exceeds limit {thresholds.max_frame_loss_pct:.1f}%"
        )

    if stats.mean_fps < thresholds.min_fps:
        failures.append(
            f"Mean FPS {stats.mean_fps:.1f} "
            f"below minimum {thresholds.min_fps:.1f}"
        )

    if stats.mean_jitter_ms > thresholds.max_jitter_ms:
        failures.append(
            f"Mean jitter {stats.mean_jitter_ms:.1f} ms "
            f"exceeds limit {thresholds.max_jitter_ms:.1f} ms"
        )

    return ValidationResult(passed=len(failures) == 0, failures=failures)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile(sorted_values: List[float], pct: float) -> float:
    """Return the *pct*-th percentile of a pre-sorted list."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = (pct / 100.0) * (n - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_values[lo]
    fraction = idx - lo
    return sorted_values[lo] * (1 - fraction) + sorted_values[hi] * fraction


def _compute_jitter_ms(completion_times: List[float]) -> float:
    """Compute mean absolute deviation of inter-frame intervals (ms)."""
    if len(completion_times) < 2:
        return 0.0
    intervals = [
        (completion_times[i + 1] - completion_times[i]) * 1000.0
        for i in range(len(completion_times) - 1)
    ]
    mean_interval = sum(intervals) / len(intervals)
    mad = sum(abs(iv - mean_interval) for iv in intervals) / len(intervals)
    return mad
