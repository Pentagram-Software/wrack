"""Low-Latency HLS (LL-HLS) playlist generator.

Produces standards-compliant M3U8 playlists according to
RFC 8216bis (Apple's LL-HLS specification draft):

* **Media playlist** (``stream.m3u8``) – contains ``#EXT-X-PART``
  tags for each partial segment, ``#EXTINF`` + URI for each completed
  segment, ``#EXT-X-PRELOAD-HINT`` pointing at the next partial
  segment, and the ``#EXT-X-SERVER-CONTROL`` header enabling blocking
  playlist reload.

* **Master playlist** (``index.m3u8``) – a minimal rendition manifest
  linking to the media playlist, carrying bandwidth and codec metadata
  that allow players to select the stream.

Key LL-HLS tags (RFC 8216bis):
  - ``#EXT-X-VERSION:9``                (required for LL-HLS)
  - ``#EXT-X-SERVER-CONTROL``           (CAN-BLOCK-RELOAD, PART-HOLD-BACK)
  - ``#EXT-X-PART-INF``                 (PART-TARGET duration)
  - ``#EXT-X-PART``                     (per-part entries)
  - ``#EXT-X-PRELOAD-HINT``             (next-part hint)
"""

from typing import List

from .segment import PartialSegment, Segment


class PlaylistGenerator:
    """Generate LL-HLS M3U8 playlist text.

    Parameters
    ----------
    target_duration:
        Target full-segment duration in seconds.  The ``#EXT-X-TARGETDURATION``
        tag is set to ``ceil(target_duration)``.
    part_target:
        Target partial-segment duration in seconds.
        ``#EXT-X-PART-INF:PART-TARGET`` is set to this value.
    """

    #: ``PART-HOLD-BACK`` is required to be at least 3 × ``PART-TARGET``
    #: (RFC 8216bis §4.4.3.8).
    PART_HOLD_BACK_MULTIPLIER = 3

    def __init__(
        self,
        target_duration: float = 2.0,
        part_target: float = 0.25,
    ) -> None:
        self.target_duration = target_duration
        self.part_target = part_target

    # ------------------------------------------------------------------
    # Media playlist
    # ------------------------------------------------------------------

    def generate_media_playlist(
        self,
        segments: List[Segment],
        pending_parts: List[PartialSegment],
        media_sequence: int,
        next_segment_sequence: int,
    ) -> str:
        """Return the LL-HLS media playlist as a string.

        Args:
            segments: Completed segments to include (oldest first).
            pending_parts: Partial segments for the segment currently being
                built (not yet in *segments*).
            media_sequence: Sequence number of the *oldest* segment in
                *segments* (``#EXT-X-MEDIA-SEQUENCE`` value).
            next_segment_sequence: Sequence number that the *next* full
                segment will receive.  Used to construct the preload-hint URI.
        """
        part_hold_back = self.part_target * self.PART_HOLD_BACK_MULTIPLIER
        # #EXT-X-TARGETDURATION must be an integer >= max segment duration.
        target_duration_int = max(int(self.target_duration) + 1, 1)

        lines: List[str] = [
            "#EXTM3U",
            "#EXT-X-VERSION:9",
            f"#EXT-X-TARGETDURATION:{target_duration_int}",
            f"#EXT-X-PART-INF:PART-TARGET={self.part_target:.3f}",
            (
                f"#EXT-X-SERVER-CONTROL:"
                f"CAN-BLOCK-RELOAD=YES,"
                f"PART-HOLD-BACK={part_hold_back:.3f}"
            ),
            f"#EXT-X-MEDIA-SEQUENCE:{media_sequence}",
            "",
        ]

        # Completed segments (with their parts).
        for seg in segments:
            for part in seg.parts:
                lines.append(self._part_tag(part))
            lines.append(f"#EXTINF:{seg.duration:.5f},")
            lines.append(seg.uri)
            lines.append("")

        # Parts for the segment currently being built.
        for part in pending_parts:
            lines.append(self._part_tag(part))

        # Preload hint: the *next* part that will be available.
        if pending_parts:
            next_part_idx = pending_parts[-1].part_index + 1
            hint_seq = pending_parts[-1].sequence
        else:
            next_part_idx = 0
            hint_seq = next_segment_sequence
        hint_uri = f"part{hint_seq}_{next_part_idx}.ts"
        lines.append(f'#EXT-X-PRELOAD-HINT:TYPE=PART,URI="{hint_uri}"')

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Master playlist
    # ------------------------------------------------------------------

    def generate_master_playlist(
        self,
        media_playlist_uri: str = "stream.m3u8",
        bandwidth: int = 2_000_000,
        width: int = 1280,
        height: int = 720,
        frame_rate: float = 30.0,
        codecs: str = "avc1.42e01e",
    ) -> str:
        """Return the LL-HLS master playlist as a string.

        The codec string ``avc1.42e01e`` encodes:

        * ``42`` – Baseline profile (``0x42 = 66``)
        * ``e0`` – constraint flags
        * ``1e`` – level 3.0

        Args:
            media_playlist_uri: Relative URI to the media playlist.
            bandwidth: Peak bandwidth in bits/second.
            width: Video width in pixels.
            height: Video height in pixels.
            frame_rate: Nominal frame rate.
            codecs: RFC 6381 codec string.
        """
        stream_inf = (
            f"#EXT-X-STREAM-INF:"
            f"BANDWIDTH={bandwidth},"
            f"RESOLUTION={width}x{height},"
            f'CODECS="{codecs}",'
            f"FRAME-RATE={frame_rate:.3f}"
        )
        return (
            "#EXTM3U\n"
            f"{stream_inf}\n"
            f"{media_playlist_uri}\n"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _part_tag(part: PartialSegment) -> str:
        """Format a ``#EXT-X-PART`` tag for *part*."""
        tag = f'#EXT-X-PART:DURATION={part.duration:.5f},URI="{part.uri}"'
        if part.independent:
            tag += ",INDEPENDENT=YES"
        return tag
