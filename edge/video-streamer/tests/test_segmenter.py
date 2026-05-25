"""Unit tests for hls.segmenter – IDR detection and segmentation logic."""

import time
from pathlib import Path

import pytest

from hls.segment import PartialSegment, Segment
from hls.segmenter import (
    HLSSegmenter,
    NAL_TYPE_IDR,
    NAL_TYPE_NON_IDR,
    NAL_TYPE_PPS,
    NAL_TYPE_SPS,
    contains_idr,
    extract_sps_pps,
    find_nal_boundaries,
)
from hls.store import SegmentStore

# ---------------------------------------------------------------------------
# Helpers to build synthetic H.264 Annex B data
# ---------------------------------------------------------------------------

def _nal(nal_type: int, payload: bytes = b"\xAB\xCD") -> bytes:
    """Return a 4-byte-start-code NAL unit with the given type."""
    header = bytes([nal_type & 0x1F])
    return b"\x00\x00\x00\x01" + header + payload


def _nal3(nal_type: int, payload: bytes = b"\xAB") -> bytes:
    """Return a 3-byte-start-code NAL unit with the given type."""
    header = bytes([nal_type & 0x1F])
    return b"\x00\x00\x01" + header + payload


def _idr_frame(extra: bytes = b"") -> bytes:
    """Return a synthetic IDR (keyframe) NAL unit."""
    return _nal(NAL_TYPE_IDR, b"\xDE\xAD\xBE\xEF" + extra)


def _non_idr_frame(extra: bytes = b"") -> bytes:
    """Return a synthetic non-IDR (P-frame) NAL unit."""
    return _nal(NAL_TYPE_NON_IDR, b"\xCA\xFE" + extra)


def _sps_nal() -> bytes:
    return _nal(NAL_TYPE_SPS, b"\x64\x00\x1F")


def _pps_nal() -> bytes:
    return _nal(NAL_TYPE_PPS, b"\xEB\x8F\x2C")


# ===========================================================================
# find_nal_boundaries
# ===========================================================================

class TestFindNalBoundaries:
    def test_empty_returns_empty(self):
        assert find_nal_boundaries(b"") == []

    def test_no_start_codes_returns_empty(self):
        assert find_nal_boundaries(b"\xFF\xFF\xFF\xFF") == []

    def test_single_4byte_start_code(self):
        data = _nal(NAL_TYPE_IDR)
        result = find_nal_boundaries(data)
        assert len(result) == 1
        sc_pos, sc_len, nal_type = result[0]
        assert sc_pos == 0
        assert sc_len == 4
        assert nal_type == NAL_TYPE_IDR

    def test_single_3byte_start_code(self):
        data = _nal3(NAL_TYPE_NON_IDR)
        result = find_nal_boundaries(data)
        assert len(result) == 1
        _, sc_len, nal_type = result[0]
        assert sc_len == 3
        assert nal_type == NAL_TYPE_NON_IDR

    def test_multiple_nal_units_4byte(self):
        data = _nal(NAL_TYPE_SPS) + _nal(NAL_TYPE_PPS) + _nal(NAL_TYPE_IDR)
        result = find_nal_boundaries(data)
        types = [r[2] for r in result]
        assert types == [NAL_TYPE_SPS, NAL_TYPE_PPS, NAL_TYPE_IDR]

    def test_mixed_start_codes(self):
        data = _nal(NAL_TYPE_SPS) + _nal3(NAL_TYPE_IDR)
        result = find_nal_boundaries(data)
        assert len(result) == 2
        assert result[0][2] == NAL_TYPE_SPS
        assert result[1][2] == NAL_TYPE_IDR

    def test_nal_type_uses_low_5_bits(self):
        # NAL byte with nal_ref_idc bits set: 0x65 = 0110 0101, type = 0x05 = IDR
        data = b"\x00\x00\x00\x01\x65\xAB"
        result = find_nal_boundaries(data)
        assert result[0][2] == NAL_TYPE_IDR

    def test_non_idr_type_0x61(self):
        # 0x61 & 0x1F = 1 = NON_IDR
        data = b"\x00\x00\x00\x01\x61\xAB"
        result = find_nal_boundaries(data)
        assert result[0][2] == NAL_TYPE_NON_IDR

    def test_positions_are_of_start_codes(self):
        data = b"\xFF" * 10 + _nal(NAL_TYPE_IDR)
        result = find_nal_boundaries(data)
        assert len(result) == 1
        assert result[0][0] == 10  # start of start code


# ===========================================================================
# contains_idr
# ===========================================================================

class TestContainsIdr:
    def test_idr_frame_detected(self):
        assert contains_idr(_idr_frame()) is True

    def test_non_idr_frame_not_detected(self):
        assert contains_idr(_non_idr_frame()) is False

    def test_sps_pps_no_idr(self):
        assert contains_idr(_sps_nal() + _pps_nal()) is False

    def test_sps_pps_plus_idr(self):
        data = _sps_nal() + _pps_nal() + _idr_frame()
        assert contains_idr(data) is True

    def test_empty_bytes_false(self):
        assert contains_idr(b"") is False

    def test_3byte_start_code_idr(self):
        assert contains_idr(_nal3(NAL_TYPE_IDR)) is True

    def test_multiple_non_idr_false(self):
        data = _non_idr_frame() + _non_idr_frame() + _non_idr_frame()
        assert contains_idr(data) is False

    def test_mixed_non_idr_then_idr(self):
        data = _non_idr_frame() + _idr_frame()
        assert contains_idr(data) is True

    @pytest.mark.parametrize("nal_byte", [0x65, 0x25, 0x45, 0x05])
    def test_all_idr_ref_idc_variants(self, nal_byte):
        """NAL types where (byte & 0x1F) == 5 all count as IDR."""
        data = b"\x00\x00\x00\x01" + bytes([nal_byte]) + b"\xAB"
        assert contains_idr(data) is True


# ===========================================================================
# extract_sps_pps
# ===========================================================================

class TestExtractSpsPps:
    def test_extracts_sps(self):
        sps = _sps_nal()
        result = extract_sps_pps(sps + _non_idr_frame())
        assert sps in result

    def test_extracts_pps(self):
        pps = _pps_nal()
        result = extract_sps_pps(pps + _non_idr_frame())
        assert pps in result

    def test_extracts_both(self):
        sps = _sps_nal()
        pps = _pps_nal()
        result = extract_sps_pps(sps + pps + _idr_frame())
        assert sps in result
        assert pps in result

    def test_excludes_non_sps_pps(self):
        idr = _idr_frame()
        result = extract_sps_pps(idr)
        assert result == b""

    def test_empty_returns_empty(self):
        assert extract_sps_pps(b"") == b""


# ===========================================================================
# HLSSegmenter
# ===========================================================================

class TestHLSSegmenter:
    """Test the segmenter's boundary detection and file writing."""

    def _make_segmenter(self, tmp_path: Path, target=2.0, part_target=0.25):
        store = SegmentStore(max_segments=5)
        segmenter = HLSSegmenter(
            output_dir=tmp_path,
            store=store,
            target_duration=target,
            part_target=part_target,
            fps=30.0,
        )
        return segmenter, store

    def test_output_dir_created(self, tmp_path):
        output_dir = tmp_path / "hls_out"
        store = SegmentStore()
        HLSSegmenter(output_dir=output_dir, store=store)
        assert output_dir.exists()

    def test_no_segment_before_target_duration(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0)
        t0 = 1000.0
        # Send an IDR frame but only 0.5 s after start — below target duration.
        segmenter.feed(_sps_nal() + _pps_nal() + _idr_frame(), timestamp=t0)
        segmenter.feed(_idr_frame(), timestamp=t0 + 0.5)
        segs, _, _ = store.get_snapshot()
        assert len(segs) == 0, "No segment should be created before target_duration"

    def test_segment_created_at_idr_after_target_duration(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0)
        t0 = 1000.0
        # First IDR – starts the segment.
        segmenter.feed(_sps_nal() + _pps_nal() + _idr_frame(), timestamp=t0)
        # Several non-IDR frames.
        for i in range(1, 60):
            segmenter.feed(_non_idr_frame(), timestamp=t0 + i / 30.0)
        # IDR at t0 + 2.0 s (>= target_duration).
        segmenter.feed(_idr_frame(), timestamp=t0 + 2.0)
        segs, _, _ = store.get_snapshot()
        assert len(segs) == 1

    def test_segment_file_written_to_disk(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0)
        t0 = 1000.0
        segmenter.feed(_idr_frame(), timestamp=t0)
        for i in range(1, 60):
            segmenter.feed(_non_idr_frame(), timestamp=t0 + i / 30.0)
        segmenter.feed(_idr_frame(), timestamp=t0 + 2.0)
        segs, _, _ = store.get_snapshot()
        assert len(segs) == 1
        seg_path = tmp_path / segs[0].uri
        assert seg_path.exists(), "Segment file must be written to disk"
        assert seg_path.stat().st_size > 0

    def test_segment_sequence_increments(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0)
        t0 = 1000.0
        # First segment
        segmenter.feed(_idr_frame(), timestamp=t0)
        for i in range(1, 60):
            segmenter.feed(_non_idr_frame(), timestamp=t0 + i / 30.0)
        segmenter.feed(_idr_frame(), timestamp=t0 + 2.0)
        # Second segment
        for i in range(1, 60):
            segmenter.feed(_non_idr_frame(), timestamp=t0 + 2.0 + i / 30.0)
        segmenter.feed(_idr_frame(), timestamp=t0 + 4.0)
        segs, _, _ = store.get_snapshot()
        assert len(segs) == 2
        assert segs[0].sequence == 0
        assert segs[1].sequence == 1

    def test_partial_segment_flushed_at_part_target(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0, part_target=0.25)
        t0 = 1000.0
        segmenter.feed(_idr_frame(), timestamp=t0)
        # Feed a non-IDR frame 0.3 s later – past the part_target of 0.25 s.
        segmenter.feed(_non_idr_frame(), timestamp=t0 + 0.3)
        _, parts, _ = store.get_snapshot()
        assert len(parts) >= 1, "At least one partial segment should be flushed"

    def test_partial_segment_file_written(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0, part_target=0.25)
        t0 = 1000.0
        segmenter.feed(_idr_frame(), timestamp=t0)
        segmenter.feed(_non_idr_frame(), timestamp=t0 + 0.3)
        _, parts, _ = store.get_snapshot()
        for part in parts:
            part_path = tmp_path / part.uri
            assert part_path.exists(), f"Part file {part.uri} must exist on disk"

    def test_partial_segment_uri_naming(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0, part_target=0.25)
        t0 = 1000.0
        segmenter.feed(_idr_frame(), timestamp=t0)
        segmenter.feed(_non_idr_frame(), timestamp=t0 + 0.3)
        _, parts, _ = store.get_snapshot()
        assert len(parts) > 0
        part = parts[0]
        # URI should follow the "part<seq>_<idx>.ts" convention.
        assert part.uri.startswith("part")
        assert part.uri.endswith(".ts")
        assert f"_{part.part_index}" in part.uri

    def test_idr_partial_is_independent(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0, part_target=0.25)
        t0 = 1000.0
        # First frame is IDR and part_target hasn't elapsed yet.
        segmenter.feed(_non_idr_frame(), timestamp=t0)
        # IDR frame 0.3 s later triggers a partial flush with independent=True.
        segmenter.feed(_idr_frame(), timestamp=t0 + 0.3)
        _, parts, _ = store.get_snapshot()
        idr_parts = [p for p in parts if p.independent]
        assert len(idr_parts) >= 1

    def test_finalise_segment_manual(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0)
        t0 = 1000.0
        segmenter.feed(_idr_frame(), timestamp=t0)
        segmenter.feed(_non_idr_frame(), timestamp=t0 + 0.1)
        # Manually finalise even though target_duration hasn't elapsed.
        segmenter.finalise_segment(timestamp=t0 + 0.5)
        segs, _, _ = store.get_snapshot()
        assert len(segs) == 1

    def test_segment_duration_approximately_correct(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0)
        t0 = 1000.0
        segmenter.feed(_idr_frame(), timestamp=t0)
        for i in range(1, 60):
            segmenter.feed(_non_idr_frame(), timestamp=t0 + i / 30.0)
        segmenter.feed(_idr_frame(), timestamp=t0 + 2.0)
        segs, _, _ = store.get_snapshot()
        assert len(segs) == 1
        # Duration should be approximately 2.0 s (within 0.1 s tolerance).
        assert abs(segs[0].duration - 2.0) < 0.1

    def test_segment_byte_length_matches_file(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0)
        t0 = 1000.0
        segmenter.feed(_idr_frame(), timestamp=t0)
        for i in range(1, 60):
            segmenter.feed(_non_idr_frame(), timestamp=t0 + i / 30.0)
        segmenter.feed(_idr_frame(), timestamp=t0 + 2.0)
        segs, _, _ = store.get_snapshot()
        seg = segs[0]
        actual = (tmp_path / seg.uri).stat().st_size
        assert seg.byte_length == actual

    def test_flush_partial_manual_trigger(self, tmp_path):
        segmenter, store = self._make_segmenter(tmp_path, target=2.0, part_target=0.25)
        t0 = 1000.0
        segmenter.feed(_idr_frame(), timestamp=t0)
        segmenter.feed(_non_idr_frame(), timestamp=t0 + 0.1)
        # Not yet past part_target — manual flush at 0.3 s should trigger.
        segmenter.flush_partial(timestamp=t0 + 0.3)
        _, parts, _ = store.get_snapshot()
        assert len(parts) >= 1

    def test_segment_ts_file_is_multiple_of_188(self, tmp_path):
        """Every .ts file must be a multiple of 188 bytes (TS packet size)."""
        segmenter, store = self._make_segmenter(tmp_path, target=2.0)
        t0 = 1000.0
        segmenter.feed(_idr_frame(), timestamp=t0)
        for i in range(1, 30):
            segmenter.feed(_non_idr_frame(), timestamp=t0 + i / 30.0)
        segmenter.feed(_idr_frame(), timestamp=t0 + 2.0)
        segs, _, _ = store.get_snapshot()
        assert len(segs) == 1
        ts_size = (tmp_path / segs[0].uri).stat().st_size
        assert ts_size % 188 == 0, f"TS file size {ts_size} not multiple of 188"

    def test_partial_ts_file_is_multiple_of_188(self, tmp_path):
        """Partial segment .ts files must also be multiples of 188 bytes."""
        segmenter, store = self._make_segmenter(tmp_path, target=2.0, part_target=0.25)
        t0 = 1000.0
        segmenter.feed(_idr_frame(), timestamp=t0)
        segmenter.feed(_non_idr_frame(), timestamp=t0 + 0.3)
        _, parts, _ = store.get_snapshot()
        assert len(parts) >= 1
        for part in parts:
            size = (tmp_path / part.uri).stat().st_size
            assert size % 188 == 0, f"Part file {part.uri} size {size} not multiple of 188"

    def test_sps_pps_cached_and_prepended(self, tmp_path):
        """SPS/PPS should be cached and included at segment boundaries."""
        segmenter, store = self._make_segmenter(tmp_path, target=2.0)
        t0 = 1000.0
        sps_pps = _sps_nal() + _pps_nal()
        # Feed SPS/PPS + IDR to populate the cache.
        segmenter.feed(sps_pps + _idr_frame(), timestamp=t0)
        # After feeding the SPS/PPS, the cache should be populated.
        assert segmenter._sps_pps == sps_pps
