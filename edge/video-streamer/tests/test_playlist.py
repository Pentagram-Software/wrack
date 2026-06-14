"""Unit tests for hls.playlist – LL-HLS M3U8 playlist generation."""

import pytest

from hls.playlist import PlaylistGenerator
from hls.segment import PartialSegment, Segment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _part(sequence: int, part_index: int, duration: float = 0.25,
          independent: bool = False) -> PartialSegment:
    return PartialSegment(
        sequence=sequence,
        part_index=part_index,
        duration=duration,
        uri=f"part{sequence}_{part_index}.ts",
        independent=independent,
        byte_length=1024,
    )


def _segment(sequence: int, duration: float = 2.0,
             parts: list = None) -> Segment:
    return Segment(
        sequence=sequence,
        duration=duration,
        uri=f"seg{sequence}.ts",
        byte_length=4096,
        parts=parts or [],
    )


def _default_generator() -> PlaylistGenerator:
    return PlaylistGenerator(target_duration=2.0, part_target=0.25)


# ===========================================================================
# Media playlist – required LL-HLS header tags
# ===========================================================================

class TestMediaPlaylistHeaders:
    def test_starts_with_extm3u(self):
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert pl.startswith("#EXTM3U\n")

    def test_contains_version_9(self):
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert "#EXT-X-VERSION:9" in pl

    def test_contains_target_duration(self):
        gen = PlaylistGenerator(target_duration=2.0, part_target=0.25)
        pl = gen.generate_media_playlist([], [], 0, 0)
        # TARGETDURATION must be >= max segment duration; generator adds 1.
        assert "#EXT-X-TARGETDURATION:3" in pl

    def test_target_duration_rounds_up(self):
        gen = PlaylistGenerator(target_duration=1.5, part_target=0.25)
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert "#EXT-X-TARGETDURATION:2" in pl

    def test_target_duration_minimum_1(self):
        gen = PlaylistGenerator(target_duration=0.5, part_target=0.1)
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert "#EXT-X-TARGETDURATION:1" in pl

    def test_contains_part_inf(self):
        gen = PlaylistGenerator(target_duration=2.0, part_target=0.25)
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert "#EXT-X-PART-INF:PART-TARGET=0.250" in pl

    def test_part_inf_uses_configured_part_target(self):
        gen = PlaylistGenerator(target_duration=2.0, part_target=0.33)
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert "#EXT-X-PART-INF:PART-TARGET=0.330" in pl

    def test_contains_server_control(self):
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert "#EXT-X-SERVER-CONTROL:" in pl

    def test_server_control_can_block_reload(self):
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert "CAN-BLOCK-RELOAD=YES" in pl

    def test_server_control_part_hold_back_is_3x_part_target(self):
        gen = PlaylistGenerator(target_duration=2.0, part_target=0.25)
        pl = gen.generate_media_playlist([], [], 0, 0)
        # PART-HOLD-BACK = 3 × 0.25 = 0.750
        assert "PART-HOLD-BACK=0.750" in pl

    def test_server_control_part_hold_back_scales_with_part_target(self):
        gen = PlaylistGenerator(target_duration=2.0, part_target=0.5)
        pl = gen.generate_media_playlist([], [], 0, 0)
        # PART-HOLD-BACK = 3 × 0.5 = 1.500
        assert "PART-HOLD-BACK=1.500" in pl

    def test_contains_media_sequence(self):
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], media_sequence=5, next_segment_sequence=5)
        assert "#EXT-X-MEDIA-SEQUENCE:5" in pl

    def test_media_sequence_zero_by_default(self):
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert "#EXT-X-MEDIA-SEQUENCE:0" in pl

    def test_ends_with_newline(self):
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert pl.endswith("\n")


# ===========================================================================
# Media playlist – completed segments
# ===========================================================================

class TestMediaPlaylistSegments:
    def test_single_segment_extinf_and_uri(self):
        gen = _default_generator()
        seg = _segment(0, duration=2.0)
        pl = gen.generate_media_playlist([seg], [], 0, 1)
        assert "#EXTINF:2.00000," in pl
        assert "seg0.ts" in pl

    def test_multiple_segments_in_order(self):
        gen = _default_generator()
        segs = [_segment(i, duration=2.0) for i in range(3)]
        pl = gen.generate_media_playlist(segs, [], 0, 3)
        lines = pl.splitlines()
        uri_lines = [l for l in lines if l.endswith(".ts") and l.startswith("seg")]
        assert uri_lines == ["seg0.ts", "seg1.ts", "seg2.ts"]

    def test_extinf_duration_precision(self):
        gen = _default_generator()
        seg = _segment(0, duration=1.98765)
        pl = gen.generate_media_playlist([seg], [], 0, 1)
        assert "#EXTINF:1.98765," in pl

    def test_empty_segments_no_extinf(self):
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert "#EXTINF" not in pl

    def test_segment_uri_follows_extinf(self):
        """The segment URI must appear on the line immediately after #EXTINF."""
        gen = _default_generator()
        seg = _segment(0, duration=2.0)
        pl = gen.generate_media_playlist([seg], [], 0, 1)
        lines = pl.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("#EXTINF:"):
                assert lines[i + 1] == "seg0.ts"
                break


# ===========================================================================
# Media playlist – EXT-X-PART tags for completed segments
# ===========================================================================

class TestMediaPlaylistPartsOfCompletedSegments:
    def test_ext_x_part_before_extinf(self):
        gen = _default_generator()
        p0 = _part(0, 0)
        seg = _segment(0, duration=2.0, parts=[p0])
        pl = gen.generate_media_playlist([seg], [], 0, 1)
        lines = pl.splitlines()
        part_idx = next(i for i, l in enumerate(lines) if l.startswith("#EXT-X-PART:"))
        extinf_idx = next(i for i, l in enumerate(lines) if l.startswith("#EXTINF:"))
        assert part_idx < extinf_idx

    def test_part_duration_in_tag(self):
        gen = _default_generator()
        p0 = _part(0, 0, duration=0.25123)
        seg = _segment(0, parts=[p0])
        pl = gen.generate_media_playlist([seg], [], 0, 1)
        assert "DURATION=0.25123" in pl

    def test_part_uri_in_tag(self):
        gen = _default_generator()
        p0 = _part(0, 0)
        seg = _segment(0, parts=[p0])
        pl = gen.generate_media_playlist([seg], [], 0, 1)
        assert 'URI="part0_0.ts"' in pl

    def test_independent_yes_for_idr_part(self):
        gen = _default_generator()
        p0 = _part(0, 0, independent=True)
        seg = _segment(0, parts=[p0])
        pl = gen.generate_media_playlist([seg], [], 0, 1)
        assert "INDEPENDENT=YES" in pl

    def test_no_independent_for_non_idr_part(self):
        gen = _default_generator()
        p0 = _part(0, 0, independent=False)
        seg = _segment(0, parts=[p0])
        pl = gen.generate_media_playlist([seg], [], 0, 1)
        # INDEPENDENT=YES should not appear for non-IDR parts.
        assert "INDEPENDENT=YES" not in pl

    def test_multiple_parts_per_segment(self):
        gen = _default_generator()
        parts = [_part(0, i) for i in range(4)]
        seg = _segment(0, parts=parts)
        pl = gen.generate_media_playlist([seg], [], 0, 1)
        part_lines = [l for l in pl.splitlines() if l.startswith("#EXT-X-PART:")]
        assert len(part_lines) == 4


# ===========================================================================
# Media playlist – pending partial segments
# ===========================================================================

class TestMediaPlaylistPendingParts:
    def test_pending_parts_appear_after_completed_segments(self):
        gen = _default_generator()
        seg = _segment(0, parts=[_part(0, 0)])
        pending = [_part(1, 0), _part(1, 1)]
        pl = gen.generate_media_playlist([seg], pending, 0, 1)
        # The last seg URI should appear before pending parts.
        seg_uri_idx = pl.index("seg0.ts")
        pending_part_uri_idx = pl.index("part1_0.ts")
        assert seg_uri_idx < pending_part_uri_idx

    def test_pending_parts_count(self):
        gen = _default_generator()
        pending = [_part(0, 0), _part(0, 1), _part(0, 2)]
        pl = gen.generate_media_playlist([], pending, 0, 0)
        part_lines = [l for l in pl.splitlines() if l.startswith("#EXT-X-PART:")]
        assert len(part_lines) == 3

    def test_no_pending_parts_no_duplicate_part_tags(self):
        gen = _default_generator()
        seg = _segment(0, parts=[_part(0, 0)])
        pl = gen.generate_media_playlist([seg], [], 0, 1)
        # With one completed segment and no pending parts,
        # there should be exactly one EXT-X-PART line.
        part_lines = [l for l in pl.splitlines() if l.startswith("#EXT-X-PART:")]
        assert len(part_lines) == 1


# ===========================================================================
# Media playlist – EXT-X-PRELOAD-HINT
# ===========================================================================

class TestMediaPlaylistPreloadHint:
    def test_preload_hint_present(self):
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert "#EXT-X-PRELOAD-HINT:" in pl

    def test_preload_hint_type_part(self):
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], 0, 0)
        assert "TYPE=PART" in pl

    def test_preload_hint_uri_when_no_pending_parts(self):
        """When no parts are pending, hint points at part 0 of next_segment_sequence."""
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], 0, next_segment_sequence=2)
        assert 'URI="part2_0.ts"' in pl

    def test_preload_hint_uri_increments_after_pending_parts(self):
        """Hint URI should point at the part *after* the last pending part."""
        gen = _default_generator()
        pending = [_part(1, 0), _part(1, 1)]
        pl = gen.generate_media_playlist([], pending, 0, next_segment_sequence=1)
        # Last pending part is index 1, so hint should be index 2.
        assert 'URI="part1_2.ts"' in pl

    def test_preload_hint_is_last_meaningful_line(self):
        gen = _default_generator()
        pl = gen.generate_media_playlist([], [], 0, 0)
        lines = [l for l in pl.splitlines() if l.strip()]
        assert lines[-1].startswith("#EXT-X-PRELOAD-HINT:")


# ===========================================================================
# Master playlist
# ===========================================================================

class TestMasterPlaylist:
    def test_starts_with_extm3u(self):
        gen = _default_generator()
        pl = gen.generate_master_playlist()
        assert pl.startswith("#EXTM3U\n")

    def test_contains_stream_inf(self):
        gen = _default_generator()
        pl = gen.generate_master_playlist()
        assert "#EXT-X-STREAM-INF:" in pl

    def test_default_media_playlist_uri(self):
        gen = _default_generator()
        pl = gen.generate_master_playlist()
        assert "stream.m3u8" in pl

    def test_custom_media_playlist_uri(self):
        gen = _default_generator()
        pl = gen.generate_master_playlist(media_playlist_uri="live/stream.m3u8")
        assert "live/stream.m3u8" in pl

    def test_bandwidth_in_stream_inf(self):
        gen = _default_generator()
        pl = gen.generate_master_playlist(bandwidth=4_000_000)
        assert "BANDWIDTH=4000000" in pl

    def test_resolution_in_stream_inf(self):
        gen = _default_generator()
        pl = gen.generate_master_playlist(width=1280, height=720)
        assert "RESOLUTION=1280x720" in pl

    def test_codecs_in_stream_inf(self):
        gen = _default_generator()
        pl = gen.generate_master_playlist(codecs="avc1.42e01e")
        assert 'CODECS="avc1.42e01e"' in pl

    def test_frame_rate_in_stream_inf(self):
        gen = _default_generator()
        pl = gen.generate_master_playlist(frame_rate=30.0)
        assert "FRAME-RATE=30.000" in pl

    def test_ends_with_newline(self):
        gen = _default_generator()
        pl = gen.generate_master_playlist()
        assert pl.endswith("\n")

    def test_stream_inf_before_uri(self):
        gen = _default_generator()
        pl = gen.generate_master_playlist()
        lines = pl.splitlines()
        inf_idx = next(i for i, l in enumerate(lines) if l.startswith("#EXT-X-STREAM-INF:"))
        uri_idx = next(i for i, l in enumerate(lines) if l == "stream.m3u8")
        assert inf_idx + 1 == uri_idx


# ===========================================================================
# PlaylistGenerator configuration
# ===========================================================================

class TestPlaylistGeneratorConfig:
    def test_default_target_duration(self):
        gen = PlaylistGenerator()
        assert gen.target_duration == 2.0

    def test_default_part_target(self):
        gen = PlaylistGenerator()
        assert gen.part_target == 0.25

    def test_custom_target_duration(self):
        gen = PlaylistGenerator(target_duration=4.0)
        assert gen.target_duration == 4.0

    def test_custom_part_target(self):
        gen = PlaylistGenerator(part_target=0.5)
        assert gen.part_target == 0.5

    @pytest.mark.parametrize("part_target,expected_hold_back", [
        (0.25, 0.75),
        (0.5, 1.5),
        (1.0, 3.0),
    ])
    def test_part_hold_back_is_3x_part_target(self, part_target, expected_hold_back):
        gen = PlaylistGenerator(target_duration=2.0, part_target=part_target)
        pl = gen.generate_media_playlist([], [], 0, 0)
        expected_str = f"PART-HOLD-BACK={expected_hold_back:.3f}"
        assert expected_str in pl
