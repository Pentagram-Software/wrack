"""Unit tests for latency_metrics module."""

import sys
import time
from pathlib import Path

import pytest

# Allow importing from parent directory without package install
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from latency_metrics import (
    FrameLatencyTracker,
    FrameTimingRecord,
    LatencyStats,
    WANQualityThresholds,
    ValidationResult,
    validate_latency_results,
    _percentile,
    _compute_jitter_ms,
)


# ---------------------------------------------------------------------------
# FrameTimingRecord
# ---------------------------------------------------------------------------


class TestFrameTimingRecord:
    def test_assembly_latency_ms_basic(self):
        """assembly_latency_ms returns delta in milliseconds."""
        rec = FrameTimingRecord(
            frame_id=1,
            first_chunk_ts=0.0,
            complete_ts=0.05,  # 50 ms later
            chunk_count=3,
            byte_size=3600,
        )
        assert abs(rec.assembly_latency_ms - 50.0) < 1e-9

    def test_assembly_latency_ms_zero(self):
        """assembly_latency_ms is 0 when timestamps are equal."""
        rec = FrameTimingRecord(
            frame_id=0,
            first_chunk_ts=1.0,
            complete_ts=1.0,
            chunk_count=1,
            byte_size=100,
        )
        assert rec.assembly_latency_ms == 0.0


# ---------------------------------------------------------------------------
# FrameLatencyTracker
# ---------------------------------------------------------------------------


class TestFrameLatencyTracker:
    def _feed_frame(self, tracker, frame_id, byte_size=1200, chunk_count=1, delta_s=0.01):
        """Helper: record first chunk then complete the frame after delta_s."""
        tracker.record_first_chunk(frame_id, chunk_count, byte_size)
        time.sleep(delta_s)
        return tracker.record_complete(frame_id)

    def test_record_complete_returns_record(self):
        """record_complete returns a FrameTimingRecord for a tracked frame."""
        tracker = FrameLatencyTracker()
        tracker.record_first_chunk(0, 1, 1200)
        record = tracker.record_complete(0)
        assert isinstance(record, FrameTimingRecord)
        assert record.frame_id == 0
        assert record.chunk_count == 1
        assert record.byte_size == 1200

    def test_record_complete_returns_none_for_unknown_frame(self):
        """record_complete returns None when frame was not started."""
        tracker = FrameLatencyTracker()
        assert tracker.record_complete(99) is None

    def test_completed_count_increments(self):
        """completed_count reflects the number of fully received frames."""
        tracker = FrameLatencyTracker()
        assert tracker.completed_count == 0
        tracker.record_first_chunk(0, 1, 100)
        tracker.record_complete(0)
        assert tracker.completed_count == 1
        tracker.record_first_chunk(1, 2, 200)
        tracker.record_complete(1)
        assert tracker.completed_count == 2

    def test_assembly_latency_is_positive(self):
        """Assembly latency is positive when complete_ts > first_chunk_ts."""
        tracker = FrameLatencyTracker()
        self._feed_frame(tracker, 0, delta_s=0.005)
        stats = tracker.compute_stats()
        assert stats.mean_assembly_ms > 0

    def test_drop_stale_frames_removes_incomplete(self):
        """drop_stale_frames purges frames older than max_age_s."""
        tracker = FrameLatencyTracker()
        tracker.record_first_chunk(5, 3, 3600)
        # Patch the pending entry to simulate staleness
        tracker._pending[5]["first_ts"] -= 10.0  # 10 seconds ago
        dropped = tracker.drop_stale_frames(max_age_s=2.0)
        assert dropped == 1
        assert 5 not in tracker._pending

    def test_drop_stale_frames_keeps_fresh_frames(self):
        """drop_stale_frames leaves recently started frames alone."""
        tracker = FrameLatencyTracker()
        tracker.record_first_chunk(7, 2, 2400)
        dropped = tracker.drop_stale_frames(max_age_s=5.0)
        assert dropped == 0
        assert 7 in tracker._pending

    def test_compute_stats_empty_returns_zero_samples(self):
        """compute_stats on an empty tracker returns sample_count=0."""
        tracker = FrameLatencyTracker()
        stats = tracker.compute_stats()
        assert stats.sample_count == 0

    def test_compute_stats_sample_count(self):
        """compute_stats returns correct sample_count."""
        tracker = FrameLatencyTracker(expected_fps=30.0)
        for i in range(10):
            tracker.record_first_chunk(i, 1, 100)
            tracker.record_complete(i)
        stats = tracker.compute_stats()
        assert stats.sample_count == 10

    def test_compute_stats_rtt_propagated(self):
        """rtt_ms passed to compute_stats appears in LatencyStats."""
        tracker = FrameLatencyTracker()
        tracker.record_first_chunk(0, 1, 100)
        tracker.record_complete(0)
        stats = tracker.compute_stats(rtt_ms=42.5)
        assert stats.rtt_ms == pytest.approx(42.5)

    def test_compute_stats_fps_reasonable(self):
        """mean_fps is reasonable given n frames over ~duration."""
        tracker = FrameLatencyTracker(expected_fps=30.0)
        for i in range(30):
            tracker.record_first_chunk(i, 1, 100)
            tracker.record_complete(i)
        stats = tracker.compute_stats()
        # Duration is ~0 s (no sleep), so fps will be very high – just confirm > 0
        assert stats.mean_fps > 0

    def test_reset_clears_state(self):
        """reset removes all records and pending frames."""
        tracker = FrameLatencyTracker()
        tracker.record_first_chunk(0, 1, 100)
        tracker.record_complete(0)
        tracker.record_first_chunk(1, 1, 100)
        tracker.reset()
        assert tracker.completed_count == 0
        assert len(tracker._pending) == 0
        assert tracker._session_start is None


# ---------------------------------------------------------------------------
# LatencyStats.to_dict
# ---------------------------------------------------------------------------


class TestLatencyStatsToDict:
    def test_to_dict_keys_present(self):
        """to_dict includes all expected keys."""
        stats = LatencyStats(
            sample_count=5,
            duration_s=1.0,
            mean_assembly_ms=10.0,
            median_assembly_ms=9.5,
            p95_assembly_ms=20.0,
            p99_assembly_ms=25.0,
            max_assembly_ms=30.0,
            mean_fps=25.0,
            frame_loss_pct=0.5,
            mean_jitter_ms=3.0,
            rtt_ms=15.0,
        )
        d = stats.to_dict()
        for key in [
            "sample_count",
            "duration_s",
            "mean_assembly_ms",
            "median_assembly_ms",
            "p95_assembly_ms",
            "p99_assembly_ms",
            "max_assembly_ms",
            "mean_fps",
            "frame_loss_pct",
            "mean_jitter_ms",
            "rtt_ms",
        ]:
            assert key in d

    def test_to_dict_rtt_none_preserved(self):
        """rtt_ms=None is preserved in to_dict output."""
        stats = LatencyStats()
        assert stats.to_dict()["rtt_ms"] is None


# ---------------------------------------------------------------------------
# validate_latency_results
# ---------------------------------------------------------------------------


class TestValidateLatencyResults:
    def _make_stats(self, **overrides) -> LatencyStats:
        base = LatencyStats(
            sample_count=100,
            duration_s=10.0,
            mean_assembly_ms=30.0,
            median_assembly_ms=28.0,
            p95_assembly_ms=60.0,
            p99_assembly_ms=80.0,
            max_assembly_ms=120.0,
            mean_fps=25.0,
            frame_loss_pct=1.0,
            mean_jitter_ms=10.0,
            rtt_ms=50.0,
        )
        for k, v in overrides.items():
            setattr(base, k, v)
        return base

    def test_pass_when_all_within_thresholds(self):
        """Validation passes when all metrics meet default thresholds."""
        stats = self._make_stats()
        result = validate_latency_results(stats)
        assert result.passed is True
        assert result.failures == []

    def test_fail_when_no_frames(self):
        """Validation fails with descriptive message when no frames received."""
        result = validate_latency_results(LatencyStats())
        assert result.passed is False
        assert any("No frames" in f for f in result.failures)

    def test_fail_on_high_p95_latency(self):
        """p95 assembly latency above threshold triggers failure."""
        stats = self._make_stats(p95_assembly_ms=250.0)
        result = validate_latency_results(stats, WANQualityThresholds(max_assembly_ms_p95=200.0))
        assert result.passed is False
        assert any("p95" in f for f in result.failures)

    def test_fail_on_high_frame_loss(self):
        """Excessive frame loss triggers failure."""
        stats = self._make_stats(frame_loss_pct=8.0)
        result = validate_latency_results(stats, WANQualityThresholds(max_frame_loss_pct=5.0))
        assert result.passed is False
        assert any("loss" in f.lower() for f in result.failures)

    def test_fail_on_low_fps(self):
        """FPS below minimum triggers failure."""
        stats = self._make_stats(mean_fps=10.0)
        result = validate_latency_results(stats, WANQualityThresholds(min_fps=20.0))
        assert result.passed is False
        assert any("FPS" in f for f in result.failures)

    def test_fail_on_high_jitter(self):
        """Excessive jitter triggers failure."""
        stats = self._make_stats(mean_jitter_ms=80.0)
        result = validate_latency_results(stats, WANQualityThresholds(max_jitter_ms=50.0))
        assert result.passed is False
        assert any("jitter" in f.lower() for f in result.failures)

    def test_multiple_failures_reported(self):
        """All violated thresholds are reported, not just the first."""
        stats = self._make_stats(
            p95_assembly_ms=500.0,
            frame_loss_pct=20.0,
            mean_fps=5.0,
            mean_jitter_ms=200.0,
        )
        result = validate_latency_results(stats)
        assert result.passed is False
        assert len(result.failures) >= 4

    def test_uses_default_thresholds_when_none_given(self):
        """None thresholds argument uses WANQualityThresholds defaults."""
        stats = self._make_stats()
        result = validate_latency_results(stats, None)
        assert result.passed is True

    def test_validation_result_to_dict(self):
        """ValidationResult.to_dict contains 'passed' and 'failures' keys."""
        result = ValidationResult(passed=True, failures=[])
        d = result.to_dict()
        assert "passed" in d
        assert "failures" in d


# ---------------------------------------------------------------------------
# _percentile helper
# ---------------------------------------------------------------------------


class TestPercentile:
    def test_p50_of_uniform_list(self):
        """p50 of [1,2,3,4,5] is the middle value (3)."""
        result = _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50)
        assert result == pytest.approx(3.0)

    def test_p0_returns_minimum(self):
        """p0 returns the smallest element."""
        values = [10.0, 20.0, 30.0]
        assert _percentile(values, 0) == pytest.approx(10.0)

    def test_p100_returns_maximum(self):
        """p100 returns the largest element."""
        values = [10.0, 20.0, 30.0]
        assert _percentile(values, 100) == pytest.approx(30.0)

    def test_empty_returns_zero(self):
        """Empty list returns 0.0."""
        assert _percentile([], 50) == 0.0

    def test_single_element(self):
        """Single-element list returns that element for any percentile."""
        assert _percentile([42.0], 95) == pytest.approx(42.0)

    def test_interpolation_between_samples(self):
        """p50 of [1, 3] interpolates to 2.0."""
        result = _percentile([1.0, 3.0], 50)
        assert result == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# _compute_jitter_ms helper
# ---------------------------------------------------------------------------


class TestComputeJitterMs:
    def test_equal_intervals_give_zero_jitter(self):
        """Perfectly evenly spaced frames produce zero jitter."""
        times = [i * 0.033 for i in range(10)]  # ~30 fps
        jitter = _compute_jitter_ms(times)
        assert jitter == pytest.approx(0.0, abs=1e-9)

    def test_single_interval_gives_zero(self):
        """Two timestamps (one interval) produce 0 MAD."""
        jitter = _compute_jitter_ms([0.0, 0.1])
        assert jitter == pytest.approx(0.0)

    def test_varied_intervals_produce_nonzero_jitter(self):
        """Non-uniform intervals produce positive jitter."""
        times = [0.0, 0.01, 0.05, 0.06, 0.12]
        jitter = _compute_jitter_ms(times)
        assert jitter > 0

    def test_empty_list_gives_zero(self):
        """Empty list gives 0.0."""
        assert _compute_jitter_ms([]) == 0.0

    def test_single_element_gives_zero(self):
        """Single timestamp (no intervals) gives 0.0."""
        assert _compute_jitter_ms([1.0]) == 0.0
