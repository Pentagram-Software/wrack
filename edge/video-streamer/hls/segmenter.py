"""HLS segmenter: splits an H.264 Annex B stream into LL-HLS segments.

The :class:`HLSSegmenter` is the heart of the LL-HLS pipeline.  It accepts
raw H.264 Annex B data via :meth:`HLSSegmenter.feed`, detects IDR (keyframe)
boundaries, and produces:

* **Partial segments** – flushed every *part_target* seconds so that
  LL-HLS clients can display content with low additional latency.
* **Full segments** – closed at the next IDR boundary after
  *target_duration* seconds have elapsed.

Both partial and full segments are written to *output_dir* and registered
with a :class:`~hls.store.SegmentStore` so the playlist generator and
HTTP server always see a consistent, up-to-date view.

Usage on the Pi::

    store = SegmentStore()
    segmenter = HLSSegmenter(output_dir=Path("/tmp/hls"), store=store)
    # From a Picamera2 output callback:
    segmenter.feed(h264_bytes, timestamp=time.time())

Thread-safety
-------------
:meth:`feed` may be called from any thread (e.g. a Picamera2 output
callback).  All internal state is protected by a :class:`threading.Lock`.
"""

import logging
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

from .muxer import frames_to_ts_segment, mux_h264_to_ts
from .segment import PartialSegment, Segment
from .store import SegmentStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# H.264 Annex B NAL unit type constants
# ---------------------------------------------------------------------------
NAL_TYPE_NON_IDR = 1   # Non-IDR slice (P-frame / B-frame)
NAL_TYPE_IDR = 5        # Instantaneous Decoding Refresh (keyframe / I-frame)
NAL_TYPE_SPS = 7        # Sequence Parameter Set
NAL_TYPE_PPS = 8        # Picture Parameter Set

# 4-byte and 3-byte Annex B start codes
_SC4 = b"\x00\x00\x00\x01"
_SC3 = b"\x00\x00\x01"


# ---------------------------------------------------------------------------
# H.264 Annex B utility functions
# ---------------------------------------------------------------------------

def find_nal_boundaries(data: bytes) -> List[Tuple[int, int, int]]:
    """Locate all NAL units in an H.264 Annex B buffer.

    Returns a list of ``(start_of_start_code, start_code_length, nal_type)``
    tuples in buffer order.

    Args:
        data: Raw H.264 Annex B byte string (may contain multiple NAL units).

    Returns:
        List of tuples; empty if no start codes are found.
    """
    results: List[Tuple[int, int, int]] = []
    i = 0
    n = len(data)
    while i < n:
        if data[i: i + 4] == _SC4 and i + 4 < n:
            nal_type = data[i + 4] & 0x1F
            results.append((i, 4, nal_type))
            i += 4
        elif data[i: i + 3] == _SC3 and i + 3 < n:
            nal_type = data[i + 3] & 0x1F
            results.append((i, 3, nal_type))
            i += 3
        else:
            i += 1
    return results


def contains_idr(data: bytes) -> bool:
    """Return ``True`` if *data* contains at least one IDR NAL unit.

    This is the fast path used by :class:`HLSSegmenter` to decide whether
    a received chunk can open a new segment.

    Args:
        data: Raw H.264 Annex B byte string.
    """
    for _, _, nal_type in find_nal_boundaries(data):
        if nal_type == NAL_TYPE_IDR:
            return True
    return False


def extract_sps_pps(data: bytes) -> bytes:
    """Extract all SPS and PPS NAL units from *data* (Annex B format).

    The returned bytes include start codes and can be prepended to the
    first IDR frame of a new segment so decoders can initialise.
    """
    nals = find_nal_boundaries(data)
    boundaries_and_data = list(zip(nals, [n[0] for n in nals[1:]] + [len(data)]))
    out = bytearray()
    for (start, sc_len, nal_type), end in boundaries_and_data:
        if nal_type in (NAL_TYPE_SPS, NAL_TYPE_PPS):
            out.extend(data[start:end])
    return bytes(out)


# ---------------------------------------------------------------------------
# HLSSegmenter
# ---------------------------------------------------------------------------

class HLSSegmenter:
    """Segments a live H.264 Annex B stream into LL-HLS partial and full segments.

    Parameters
    ----------
    output_dir:
        Directory where segment ``.ts`` files are written.  Created if absent.
    store:
        :class:`~hls.store.SegmentStore` that receives completed segments
        and partial segments.
    target_duration:
        Target full-segment duration in seconds (default 2.0 s).  A new
        full segment is started at the next IDR boundary that occurs
        *after* this many seconds have elapsed.
    part_target:
        Target partial-segment duration in seconds (default 0.25 s).
        A new partial segment is flushed when this interval has elapsed
        *and* new data has arrived since the last flush.
    fps:
        Nominal frame rate used to compute PTS values (default 30.0).
    """

    def __init__(
        self,
        output_dir: Path,
        store: SegmentStore,
        target_duration: float = 2.0,
        part_target: float = 0.25,
        fps: float = 30.0,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._store = store
        self._target_duration = target_duration
        self._part_target = part_target
        self._fps = fps
        self._frame_duration_90khz = int(90_000 / fps)

        self._lock = threading.Lock()

        # Accumulation buffers
        self._seg_frames: List[bytes] = []   # frames for the current segment
        self._part_frames: List[bytes] = []  # frames since last part flush

        # Timing
        self._seg_start_time: Optional[float] = None
        self._part_start_time: Optional[float] = None
        self._base_pts: int = 0              # PTS of first frame in current segment

        # Counters
        self._seg_seq: int = 0              # sequence number for next segment
        self._part_index: int = 0           # part index within current segment
        self._frame_count: int = 0          # total frames since pipeline start

        # SPS/PPS cache – prepended when a new segment starts with an IDR.
        self._sps_pps: bytes = b""

        # MPEG-TS continuity counters persist across segments.
        self._video_cc: int = 0
        self._pat_cc: int = 0
        self._pmt_cc: int = 0

        self._output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def feed(self, data: bytes, timestamp: Optional[float] = None) -> None:
        """Feed a chunk of H.264 Annex B data into the segmenter.

        The chunk should correspond to one or more complete NAL units as
        delivered by a Picamera2 output callback.

        Args:
            data: Raw H.264 Annex B bytes.
            timestamp: Wall-clock time for this data (seconds since epoch).
                Defaults to ``time.time()`` when *None*.
        """
        if not data:
            return
        if timestamp is None:
            timestamp = time.time()

        with self._lock:
            # Cache any SPS/PPS NAL units for segment initialisation.
            sps_pps = extract_sps_pps(data)
            if sps_pps:
                self._sps_pps = sps_pps

            is_idr = contains_idr(data)

            # Initialise timing on first frame.
            if self._seg_start_time is None:
                self._seg_start_time = timestamp
                self._part_start_time = timestamp

            elapsed_seg = timestamp - self._seg_start_time
            elapsed_part = timestamp - (self._part_start_time or timestamp)

            # Decide whether to close the current segment and open a new one.
            if (
                is_idr
                and elapsed_seg >= self._target_duration
                and (self._seg_frames or self._part_frames)
            ):
                self._finalise_segment(timestamp)

            # Decide whether to flush a partial segment.
            if elapsed_part >= self._part_target and self._part_frames:
                self._flush_partial(timestamp, independent=is_idr)

            # Accumulate data.
            self._seg_frames.append(data)
            self._part_frames.append(data)
            self._frame_count += 1

    def flush_partial(self, timestamp: Optional[float] = None) -> None:
        """Manually flush a partial segment if data is available.

        Useful when the caller drives the flush cadence externally (e.g.
        in a timer callback) rather than relying on elapsed time inside
        :meth:`feed`.
        """
        if timestamp is None:
            timestamp = time.time()
        with self._lock:
            if self._part_frames and self._part_start_time is not None:
                elapsed = timestamp - self._part_start_time
                if elapsed >= self._part_target:
                    self._flush_partial(timestamp)

    def finalise_segment(self, timestamp: Optional[float] = None) -> None:
        """Manually close the current segment.

        Intended for pipeline shutdown or forced segment boundaries.
        """
        if timestamp is None:
            timestamp = time.time()
        with self._lock:
            if self._seg_frames or self._part_frames:
                self._finalise_segment(timestamp)

    # ------------------------------------------------------------------
    # Internal helpers (must be called with self._lock held)
    # ------------------------------------------------------------------

    def _flush_partial(self, timestamp: float, independent: bool = False) -> None:
        """Write a partial segment file and register it with the store."""
        if not self._part_frames:
            return

        seq = self._seg_seq
        idx = self._part_index
        part_start = self._part_start_time or timestamp
        duration = max(timestamp - part_start, 0.0)

        # Convert accumulated frames to MPEG-TS.
        base_pts = self._base_pts + self._frame_duration_90khz * (
            len(self._seg_frames) - len(self._part_frames)
        )
        ts_data, self._video_cc, self._pat_cc, self._pmt_cc = _frames_to_ts(
            self._part_frames,
            base_pts,
            self._frame_duration_90khz,
            self._video_cc,
            self._pat_cc,
            self._pmt_cc,
            include_tables=(idx == 0),
        )

        filename = f"part{seq}_{idx}.ts"
        filepath = self._output_dir / filename
        filepath.write_bytes(ts_data)

        part = PartialSegment(
            sequence=seq,
            part_index=idx,
            duration=duration,
            uri=filename,
            independent=independent,
            byte_length=len(ts_data),
        )
        self._store.add_partial(part)
        logger.debug(
            "Flushed partial seg%d part%d  duration=%.3fs  size=%d bytes",
            seq, idx, duration, len(ts_data),
        )

        self._part_frames = []
        self._part_start_time = timestamp
        self._part_index += 1

    def _finalise_segment(self, timestamp: float) -> None:
        """Close the current segment, write it, and register with the store."""
        # Flush any remaining partial data first.
        if self._part_frames:
            self._flush_partial(timestamp, independent=False)

        if not self._seg_frames:
            return

        seq = self._seg_seq
        seg_start = self._seg_start_time or timestamp
        duration = max(timestamp - seg_start, 0.0)

        # Write the full segment as MPEG-TS (using the same frame list).
        ts_data = self._build_full_segment_ts()

        filename = f"seg{seq}.ts"
        filepath = self._output_dir / filename
        filepath.write_bytes(ts_data)

        # Collect the partial segments that were registered for this sequence.
        _, pending, _ = self._store.get_snapshot()
        seg_parts = [p for p in pending if p.sequence == seq]

        segment = Segment(
            sequence=seq,
            duration=duration,
            uri=filename,
            byte_length=len(ts_data),
            parts=seg_parts,
        )
        self._store.add_segment(segment)
        logger.info(
            "Finalised segment %d  duration=%.3fs  parts=%d  size=%d bytes",
            seq, duration, len(seg_parts), len(ts_data),
        )

        # Advance state for the next segment.
        # PTS continues from where this segment left off.
        self._base_pts = (
            self._base_pts + len(self._seg_frames) * self._frame_duration_90khz
        ) & 0x1_FFFF_FFFF
        self._seg_frames = []
        self._part_frames = []
        self._seg_seq += 1
        self._part_index = 0
        self._seg_start_time = timestamp
        self._part_start_time = timestamp

    def _build_full_segment_ts(self) -> bytes:
        """Re-mux all frames in the current segment into a self-contained TS."""
        # Full segments always start with PAT+PMT and include the SPS/PPS
        # prefix so decoders can initialise from any segment boundary.
        frames = self._seg_frames
        if self._sps_pps and frames and not contains_idr(frames[0]):
            # Prepend SPS/PPS if the first frame isn't already IDR-prefixed.
            frames = [self._sps_pps + frames[0]] + frames[1:]

        out = bytearray()
        video_cc = pat_cc = pmt_cc = 0  # reset for each full segment
        for i, frame in enumerate(frames):
            pts = (self._base_pts + i * self._frame_duration_90khz) & 0x1_FFFF_FFFF
            ts_chunk, video_cc, pat_cc, pmt_cc = mux_h264_to_ts(
                frame, pts,
                video_cc=video_cc, pat_cc=pat_cc, pmt_cc=pmt_cc,
                include_tables=(i == 0),
            )
            out.extend(ts_chunk)
        return bytes(out)


# ---------------------------------------------------------------------------
# Module-level helper (avoids circular import from muxer)
# ---------------------------------------------------------------------------

def _frames_to_ts(
    frames: List[bytes],
    base_pts: int,
    frame_duration_90khz: int,
    video_cc: int,
    pat_cc: int,
    pmt_cc: int,
    include_tables: bool,
):
    """Mux a list of H.264 frames into TS bytes, threading continuity counters."""
    out = bytearray()
    for i, frame in enumerate(frames):
        pts = (base_pts + i * frame_duration_90khz) & 0x1_FFFF_FFFF
        ts_chunk, video_cc, pat_cc, pmt_cc = mux_h264_to_ts(
            frame, pts,
            video_cc=video_cc, pat_cc=pat_cc, pmt_cc=pmt_cc,
            include_tables=(include_tables and i == 0),
        )
        out.extend(ts_chunk)
    return bytes(out), video_cc, pat_cc, pmt_cc
