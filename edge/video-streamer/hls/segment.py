"""HLS segment data models."""

from dataclasses import dataclass, field
import time


@dataclass
class PartialSegment:
    """A Low-Latency HLS partial segment (``#EXT-X-PART`` tag).

    Partial segments are sub-divisions of a full segment published
    *before* the full segment is complete. They allow LL-HLS clients
    to display the stream with sub-second additional latency.
    """

    sequence: int      # Parent full-segment media sequence number
    part_index: int    # 0-based index within the parent segment
    duration: float    # Duration in seconds (may be slightly less than part_target)
    uri: str           # Relative URI for this part (e.g. "part3_0.ts")
    independent: bool  # True when this part begins with a keyframe (IDR)
    byte_length: int   # Byte count of the part payload


@dataclass
class Segment:
    """A completed HLS full segment (``#EXTINF`` tag).

    Each ``Segment`` holds the list of :class:`PartialSegment` objects
    that make up its content so that the playlist can emit
    ``#EXT-X-PART`` lines before the corresponding ``#EXTINF`` line,
    as required by the LL-HLS spec (RFC 8216bis §4.4.4.9).
    """

    sequence: int
    duration: float           # Actual duration in seconds
    uri: str                  # Relative URI (e.g. "seg3.ts")
    byte_length: int          # Size of the segment file in bytes
    parts: list = field(default_factory=list)   # List[PartialSegment]
    created_at: float = field(default_factory=time.time)
