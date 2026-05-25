"""Unit tests for hls.store – SegmentStore ring buffer and blocking reload."""

import threading
import time

import pytest

from hls.segment import PartialSegment, Segment
from hls.store import SegmentStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _part(sequence: int, part_index: int, independent: bool = False) -> PartialSegment:
    return PartialSegment(
        sequence=sequence,
        part_index=part_index,
        duration=0.25,
        uri=f"part{sequence}_{part_index}.ts",
        independent=independent,
        byte_length=1024,
    )


def _segment(sequence: int, parts: list = None) -> Segment:
    return Segment(
        sequence=sequence,
        duration=2.0,
        uri=f"seg{sequence}.ts",
        byte_length=4096,
        parts=parts or [],
    )


# ===========================================================================
# Basic add / get operations
# ===========================================================================

class TestSegmentStoreBasics:
    def test_empty_store_snapshot(self):
        store = SegmentStore()
        segs, parts, msn = store.get_snapshot()
        assert segs == []
        assert parts == []
        assert msn == 0

    def test_add_partial_shows_in_snapshot(self):
        store = SegmentStore()
        store.add_partial(_part(0, 0))
        _, parts, _ = store.get_snapshot()
        assert len(parts) == 1
        assert parts[0].part_index == 0

    def test_add_multiple_partials(self):
        store = SegmentStore()
        store.add_partial(_part(0, 0))
        store.add_partial(_part(0, 1))
        _, parts, _ = store.get_snapshot()
        assert len(parts) == 2
        assert parts[0].part_index == 0
        assert parts[1].part_index == 1

    def test_add_segment_clears_pending_parts(self):
        store = SegmentStore()
        store.add_partial(_part(0, 0))
        store.add_partial(_part(0, 1))
        store.add_segment(_segment(0))
        _, parts, _ = store.get_snapshot()
        assert parts == []

    def test_add_segment_appears_in_snapshot(self):
        store = SegmentStore()
        store.add_segment(_segment(0))
        segs, _, _ = store.get_snapshot()
        assert len(segs) == 1
        assert segs[0].sequence == 0

    def test_segments_ordered_oldest_first(self):
        store = SegmentStore()
        for i in range(3):
            store.add_segment(_segment(i))
        segs, _, _ = store.get_snapshot()
        assert [s.sequence for s in segs] == [0, 1, 2]

    def test_next_segment_sequence_after_add(self):
        store = SegmentStore()
        assert store.next_segment_sequence == 0
        store.add_segment(_segment(0))
        assert store.next_segment_sequence == 1
        store.add_segment(_segment(1))
        assert store.next_segment_sequence == 2

    def test_media_sequence_initially_zero(self):
        store = SegmentStore()
        assert store.media_sequence == 0


# ===========================================================================
# Ring buffer / eviction behaviour
# ===========================================================================

class TestSegmentStoreRingBuffer:
    def test_max_segments_retained(self):
        store = SegmentStore(max_segments=3)
        for i in range(3):
            store.add_segment(_segment(i))
        segs, _, _ = store.get_snapshot()
        assert len(segs) == 3

    def test_oldest_evicted_when_full(self):
        store = SegmentStore(max_segments=3)
        for i in range(4):
            store.add_segment(_segment(i))
        segs, _, _ = store.get_snapshot()
        assert len(segs) == 3
        assert segs[0].sequence == 1  # seq 0 evicted

    def test_media_sequence_increments_on_eviction(self):
        store = SegmentStore(max_segments=3)
        for i in range(3):
            store.add_segment(_segment(i))
        assert store.media_sequence == 0
        # Adding a 4th triggers eviction.
        store.add_segment(_segment(3))
        assert store.media_sequence == 1
        store.add_segment(_segment(4))
        assert store.media_sequence == 2

    def test_media_sequence_not_incremented_before_full(self):
        store = SegmentStore(max_segments=5)
        for i in range(4):
            store.add_segment(_segment(i))
        assert store.media_sequence == 0

    def test_max_segments_one(self):
        store = SegmentStore(max_segments=1)
        store.add_segment(_segment(0))
        store.add_segment(_segment(1))
        segs, _, _ = store.get_snapshot()
        assert len(segs) == 1
        assert segs[0].sequence == 1
        assert store.media_sequence == 1

    def test_window_content_correct_after_many_evictions(self):
        store = SegmentStore(max_segments=3)
        for i in range(10):
            store.add_segment(_segment(i))
        segs, _, msn = store.get_snapshot()
        assert msn == 7
        assert [s.sequence for s in segs] == [7, 8, 9]


# ===========================================================================
# Snapshot atomicity
# ===========================================================================

class TestSnapshotAtomicity:
    def test_snapshot_returns_copy_of_segments(self):
        store = SegmentStore()
        store.add_segment(_segment(0))
        segs, _, _ = store.get_snapshot()
        # Mutating the returned list should not affect the store.
        segs.clear()
        segs2, _, _ = store.get_snapshot()
        assert len(segs2) == 1

    def test_snapshot_returns_copy_of_parts(self):
        store = SegmentStore()
        store.add_partial(_part(0, 0))
        _, parts, _ = store.get_snapshot()
        parts.clear()
        _, parts2, _ = store.get_snapshot()
        assert len(parts2) == 1


# ===========================================================================
# wait_for_part – blocking reload
# ===========================================================================

class TestWaitForPart:
    def test_returns_true_if_segment_already_present(self):
        store = SegmentStore()
        store.add_segment(_segment(0))
        result = store.wait_for_part(0, 0, timeout=1.0)
        assert result is True

    def test_returns_true_if_part_already_present(self):
        store = SegmentStore()
        store.add_partial(_part(0, 2))
        store._next_segment_sequence = 0  # keep the store pointing at seq 0
        result = store.wait_for_part(0, 2, timeout=1.0)
        assert result is True

    def test_returns_false_on_timeout(self):
        store = SegmentStore()
        start = time.monotonic()
        result = store.wait_for_part(99, 0, timeout=0.2)
        elapsed = time.monotonic() - start
        assert result is False
        # Should have waited roughly the timeout (allow generous margin).
        assert elapsed >= 0.15

    def test_returns_true_when_segment_added_from_other_thread(self):
        store = SegmentStore()
        results = []

        def waiter():
            results.append(store.wait_for_part(0, 0, timeout=2.0))

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.05)
        store.add_segment(_segment(0))
        t.join(timeout=3.0)
        assert results == [True]

    def test_returns_true_when_part_added_from_other_thread(self):
        store = SegmentStore()
        store._next_segment_sequence = 0
        results = []

        def waiter():
            results.append(store.wait_for_part(0, 1, timeout=2.0))

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.05)
        store.add_partial(_part(0, 1))
        t.join(timeout=3.0)
        assert results == [True]

    def test_superseded_sequence_returns_true_immediately(self):
        """Requesting msn=0 when msn=2 is already in the store must return True."""
        store = SegmentStore()
        store.add_segment(_segment(0))
        store.add_segment(_segment(1))
        store.add_segment(_segment(2))
        result = store.wait_for_part(0, 0, timeout=0.1)
        assert result is True

    def test_higher_part_index_already_available(self):
        """Requesting part_index=1 when part 3 is pending should be True."""
        store = SegmentStore()
        store.add_partial(_part(0, 3))
        store._next_segment_sequence = 0
        result = store.wait_for_part(0, 1, timeout=0.1)
        assert result is True

    def test_concurrent_multiple_waiters(self):
        """Multiple waiters should all be notified when a segment arrives."""
        store = SegmentStore()
        n_waiters = 5
        results = []
        lock = threading.Lock()

        def waiter():
            r = store.wait_for_part(0, 0, timeout=2.0)
            with lock:
                results.append(r)

        threads = [threading.Thread(target=waiter) for _ in range(n_waiters)]
        for t in threads:
            t.start()
        time.sleep(0.05)
        store.add_segment(_segment(0))
        for t in threads:
            t.join(timeout=3.0)

        assert results.count(True) == n_waiters


# ===========================================================================
# Thread-safety stress test
# ===========================================================================

class TestThreadSafety:
    def test_concurrent_add_and_snapshot(self):
        """No exception should occur when one thread adds segments while
        another reads snapshots."""
        store = SegmentStore(max_segments=5)
        errors = []

        def writer():
            for i in range(20):
                try:
                    store.add_segment(_segment(i))
                    time.sleep(0.001)
                except Exception as exc:
                    errors.append(exc)

        def reader():
            for _ in range(50):
                try:
                    store.get_snapshot()
                    time.sleep(0.0005)
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=writer)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert errors == [], f"Unexpected exceptions: {errors}"
