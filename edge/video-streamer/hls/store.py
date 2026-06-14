"""Thread-safe sliding-window segment store for LL-HLS delivery."""

import threading
import time
from collections import deque
from typing import List, Tuple

from .segment import PartialSegment, Segment


class SegmentStore:
    """Maintains a bounded sliding window of completed segments and the
    partial segments for the segment currently being built.

    All public methods are thread-safe.  A :class:`threading.Condition`
    is used so that :meth:`wait_for_part` can block cheaply until a
    specific ``(media-sequence, part-index)`` pair becomes available,
    supporting the LL-HLS *blocking playlist reload* mechanism
    (RFC 8216bis §6.2.5.2).
    """

    def __init__(self, max_segments: int = 5) -> None:
        """
        Args:
            max_segments: Maximum number of completed segments to retain in
                the sliding window.  When the window is full the oldest
                segment is evicted and *media_sequence* is incremented.
        """
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._segments: deque = deque(maxlen=max_segments)
        self._pending_parts: List[PartialSegment] = []
        # Sequence number of the oldest retained segment.
        self._media_sequence: int = 0
        # Sequence number of the *next* segment that will be created.
        self._next_segment_sequence: int = 0
        self._max_segments = max_segments

    # ------------------------------------------------------------------
    # Mutation API (called by HLSSegmenter)
    # ------------------------------------------------------------------

    def add_partial(self, part: PartialSegment) -> None:
        """Register a newly flushed partial segment."""
        with self._cond:
            self._pending_parts.append(part)
            self._cond.notify_all()

    def add_segment(self, segment: Segment) -> None:
        """Register a completed full segment and clear pending parts.

        When the ring buffer is full the oldest segment is implicitly
        evicted by the :class:`deque` and *media_sequence* advances
        by one to reflect the new window start.
        """
        with self._cond:
            was_full = len(self._segments) == self._max_segments
            self._segments.append(segment)
            if was_full:
                self._media_sequence += 1
            self._pending_parts = []
            self._next_segment_sequence = segment.sequence + 1
            self._cond.notify_all()

    # ------------------------------------------------------------------
    # Query API (called by playlist generator and HTTP server)
    # ------------------------------------------------------------------

    def get_snapshot(self) -> Tuple[List[Segment], List[PartialSegment], int]:
        """Return *(segments, pending_parts, media_sequence)* atomically."""
        with self._lock:
            return (
                list(self._segments),
                list(self._pending_parts),
                self._media_sequence,
            )

    @property
    def next_segment_sequence(self) -> int:
        """Sequence number assigned to the next full segment."""
        with self._lock:
            return self._next_segment_sequence

    @property
    def media_sequence(self) -> int:
        """Sequence number of the oldest retained segment."""
        with self._lock:
            return self._media_sequence

    # ------------------------------------------------------------------
    # Blocking reload support (LL-HLS §6.2.5.2)
    # ------------------------------------------------------------------

    def wait_for_part(
        self, msn: int, part_index: int, timeout: float = 10.0
    ) -> bool:
        """Block until the requested ``(msn, part_index)`` or any later
        content is available.

        Returns ``True`` when the condition is satisfied, ``False`` if
        *timeout* seconds elapse first.
        """
        deadline = time.monotonic() + timeout
        with self._cond:
            while not self._is_available(msn, part_index):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(timeout=min(remaining, 1.0))
            return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_available(self, msn: int, part_index: int) -> bool:
        """Check (without acquiring the lock) whether *msn/part_index*
        is satisfied by the current store state."""
        # Any sequence number already superseded by a full segment is OK.
        for seg in self._segments:
            if seg.sequence >= msn:
                return True

        # The requested sequence is for the segment currently in progress.
        if self._next_segment_sequence == msn:
            for part in self._pending_parts:
                if part.sequence == msn and part.part_index >= part_index:
                    return True
        elif self._next_segment_sequence > msn:
            return True

        return False
