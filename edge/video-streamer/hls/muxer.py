"""Minimal MPEG-TS muxer for wrapping H.264 Annex B video in TS packets.

This module produces standards-compliant MPEG-TS (.ts) files suitable for
HLS delivery.  It intentionally implements only the subset of MPEG-TS
needed to carry a single H.264 video elementary stream:

  - Program Association Table  (PID 0x0000)
  - Program Map Table          (PID 0x0100)
  - H.264 Video PES            (PID 0x0101)

Reference:
  ISO/IEC 13818-1:2019 (MPEG-TS)
  H.264 (ISO/IEC 14496-10 / ITU-T H.264)
"""

import struct
from typing import Tuple

# ---------------------------------------------------------------------------
# Fixed PID assignments
# ---------------------------------------------------------------------------
PID_PAT = 0x0000
PID_PMT = 0x0100
PID_VIDEO = 0x0101

# H.264 / AVC stream type (ISO/IEC 13818-1 Table 2-34)
STREAM_TYPE_H264 = 0x1B

# MPEG-2 TS packet size (fixed by standard)
TS_PACKET_SIZE = 188
# Payload capacity when there is no adaptation field
TS_PAYLOAD_SIZE = 184

# PES stream_id for video streams (ITU-T H.222.0 Table 2-18)
PES_STREAM_ID_VIDEO = 0xE0

# 90 kHz clock used for PTS/PCR timestamps
PTS_HZ = 90_000


# ---------------------------------------------------------------------------
# CRC-32/MPEG-2
# ---------------------------------------------------------------------------

def _crc32_mpeg(data: bytes) -> int:
    """Return the MPEG-2 CRC-32 of *data*."""
    crc = 0xFFFF_FFFF
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            if crc & 0x8000_0000:
                crc = ((crc << 1) ^ 0x04C1_1DB7) & 0xFFFF_FFFF
            else:
                crc = (crc << 1) & 0xFFFF_FFFF
    return crc


# ---------------------------------------------------------------------------
# TS packet construction helpers
# ---------------------------------------------------------------------------

def _ts_header(
    pid: int,
    payload_unit_start: bool,
    continuity_counter: int,
    has_adaptation: bool = False,
) -> bytes:
    """Return a 4-byte TS packet header.

    Args:
        pid: 13-bit Packet Identifier.
        payload_unit_start: Set PUSI flag (first byte of a new PES / section).
        continuity_counter: 4-bit rolling counter (0–15).
        has_adaptation: True when an adaptation field follows the header.
    """
    # adaptation_field_control:
    #   0x10 = payload only
    #   0x30 = adaptation + payload
    afc = 0x30 if has_adaptation else 0x10
    b1 = 0x47
    b2 = (0x40 if payload_unit_start else 0x00) | ((pid >> 8) & 0x1F)
    b3 = pid & 0xFF
    b4 = (afc & 0x30) | (continuity_counter & 0x0F)
    return bytes([b1, b2, b3, b4])


def _stuffed_ts_packet(
    pid: int,
    payload_unit_start: bool,
    continuity_counter: int,
    payload: bytes,
) -> bytes:
    """Build a complete 188-byte TS packet.

    If *payload* is shorter than 184 bytes the packet is padded with an
    adaptation field containing stuffing bytes (0xFF).
    """
    if len(payload) == TS_PAYLOAD_SIZE:
        return _ts_header(pid, payload_unit_start, continuity_counter) + payload

    # Need an adaptation field to absorb the padding.
    stuffing_needed = TS_PAYLOAD_SIZE - len(payload)
    if stuffing_needed == 1:
        # Only room for the adaptation_field_length byte itself (length=0).
        af = b"\x00"
    else:
        # adaptation_field_length + flags byte + stuffing
        af_len = stuffing_needed - 1
        af = bytes([af_len, 0x00]) + b"\xFF" * (af_len - 1)

    header = _ts_header(pid, payload_unit_start, continuity_counter, has_adaptation=True)
    packet = header + af + payload
    assert len(packet) == TS_PACKET_SIZE, f"packet length {len(packet)} != {TS_PACKET_SIZE}"
    return packet


# ---------------------------------------------------------------------------
# PSI tables: PAT and PMT
# ---------------------------------------------------------------------------

def _build_pat_section() -> bytes:
    """Return the raw PAT section (table_id … CRC-32)."""
    # Section body (everything between section_length and CRC):
    # transport_stream_id (2) + reserved/version/curr (1) +
    # section_number (1) + last_section_number (1) + program entry (4) = 9 bytes
    # section_length = 9 + 4 (CRC) = 13
    body = struct.pack(
        ">HBBBHH",
        0x0001,              # transport_stream_id
        0xC1,                # reserved(2)=11, version(5)=0, current_next=1
        0x00,                # section_number
        0x00,                # last_section_number
        0x0001,              # program_number = 1
        0xE000 | PID_PMT,   # reserved(3)=111, PMT_PID
    )
    section_length = len(body) + 4  # body + CRC
    header = bytes([0x00, 0xB0 | (section_length >> 8), section_length & 0xFF])
    section = header + body
    return section + struct.pack(">I", _crc32_mpeg(section))


def _build_pmt_section() -> bytes:
    """Return the raw PMT section (table_id … CRC-32)."""
    # Stream descriptor for H.264 video:
    # stream_type (1) + reserved+PID (2) + reserved+ES_info_length (2) = 5 bytes
    stream_entry = struct.pack(
        ">BHH",
        STREAM_TYPE_H264,
        0xE000 | PID_VIDEO,   # reserved(3)=111, video PID
        0xF000,               # reserved(4)=1111, ES_info_length=0
    )
    # PMT body: program_number (2) + reserved/version/curr (1) +
    # section_number (1) + last_section_number (1) +
    # reserved+PCR_PID (2) + reserved+program_info_length (2) +
    # stream_entry (5) = 14 bytes
    body = struct.pack(
        ">HBBBHH",
        0x0001,                  # program_number = 1
        0xC1,                    # reserved(2)=11, version(5)=0, current_next=1
        0x00,                    # section_number
        0x00,                    # last_section_number
        0xE000 | PID_VIDEO,     # reserved(3)=111, PCR_PID = video PID
        0xF000,                  # reserved(4)=1111, program_info_length=0
    ) + stream_entry
    section_length = len(body) + 4
    header = bytes([0x02, 0xB0 | (section_length >> 8), section_length & 0xFF])
    section = header + body
    return section + struct.pack(">I", _crc32_mpeg(section))


def _make_table_packet(pid: int, section: bytes, counter: int) -> bytes:
    """Wrap a PSI section into a single 188-byte TS packet."""
    # pointer_field = 0x00 (section starts at the first byte of the payload)
    payload = b"\x00" + section
    if len(payload) > TS_PAYLOAD_SIZE:
        raise ValueError("PSI section too large for a single TS packet")
    return _stuffed_ts_packet(pid, payload_unit_start=True, continuity_counter=counter, payload=payload)


# Pre-compute the constant PAT and PMT sections once.
_PAT_SECTION = _build_pat_section()
_PMT_SECTION = _build_pmt_section()


def make_pat_packet(counter: int = 0) -> bytes:
    """Return a complete 188-byte PAT TS packet."""
    return _make_table_packet(PID_PAT, _PAT_SECTION, counter)


def make_pmt_packet(counter: int = 0) -> bytes:
    """Return a complete 188-byte PMT TS packet."""
    return _make_table_packet(PID_PMT, _PMT_SECTION, counter)


# ---------------------------------------------------------------------------
# PTS encoding
# ---------------------------------------------------------------------------

def _encode_pts(pts: int, prefix: int = 0x21) -> bytes:
    """Encode a 33-bit PTS value into 5 bytes (ITU-T H.222.0 §2.4.3.7).

    *prefix* is ``0x21`` when only PTS is present (marker bits included).
    """
    b1 = prefix | ((pts >> 29) & 0x0E)
    b2 = (pts >> 22) & 0xFF
    b3 = ((pts >> 14) & 0xFE) | 0x01
    b4 = (pts >> 7) & 0xFF
    b5 = ((pts << 1) & 0xFE) | 0x01
    return bytes([b1, b2, b3, b4, b5])


# ---------------------------------------------------------------------------
# PES packet construction
# ---------------------------------------------------------------------------

def _make_pes_packet(h264_data: bytes, pts_90khz: int) -> bytes:
    """Return a PES packet carrying *h264_data* with *pts_90khz* timestamp."""
    pts_bytes = _encode_pts(pts_90khz & 0x1_FFFF_FFFF)
    # PES header: flags (2) + header_data_length (1) + PTS (5) = 8 bytes
    pes_header = bytes([
        0x80,   # marker=10, no scrambling, no priority, data_alignment=0, not copyrighted, not original
        0x80,   # PTS_DTS_flags=10 (PTS only), no extension flags
        0x05,   # PES_header_data_length = 5 (PTS only)
    ]) + pts_bytes
    # PES packet_length = 0 means unbounded (preferred for video)
    pes = (
        b"\x00\x00\x01"                 # start_code_prefix
        + bytes([PES_STREAM_ID_VIDEO])  # stream_id
        + b"\x00\x00"                   # PES_packet_length = 0 (unbounded)
        + pes_header
        + h264_data
    )
    return pes


# ---------------------------------------------------------------------------
# Public mux function
# ---------------------------------------------------------------------------

def mux_h264_to_ts(
    h264_data: bytes,
    pts_90khz: int,
    video_cc: int = 0,
    pat_cc: int = 0,
    pmt_cc: int = 0,
    include_tables: bool = True,
) -> Tuple[bytes, int, int, int]:
    """Wrap *h264_data* in MPEG-TS packets.

    Args:
        h264_data: Raw H.264 Annex B bitstream data for one or more NAL units.
        pts_90khz: Presentation timestamp in 90 kHz units.
        video_cc: Current continuity counter for the video PID.
        pat_cc: Current continuity counter for the PAT PID.
        pmt_cc: Current continuity counter for the PMT PID.
        include_tables: When *True* (default), prepend PAT and PMT packets.
            Set to *False* for subsequent TS packets within the same segment.

    Returns:
        A tuple ``(ts_bytes, new_video_cc, new_pat_cc, new_pmt_cc)``.
    """
    out = bytearray()

    if include_tables:
        out.extend(make_pat_packet(pat_cc))
        pat_cc = (pat_cc + 1) & 0x0F
        out.extend(make_pmt_packet(pmt_cc))
        pmt_cc = (pmt_cc + 1) & 0x0F

    pes = _make_pes_packet(h264_data, pts_90khz)

    # Slice the PES into 184-byte payload chunks and wrap each in a TS packet.
    first = True
    offset = 0
    while offset < len(pes):
        chunk = pes[offset: offset + TS_PAYLOAD_SIZE]
        out.extend(
            _stuffed_ts_packet(
                PID_VIDEO,
                payload_unit_start=first,
                continuity_counter=video_cc,
                payload=chunk,
            )
        )
        video_cc = (video_cc + 1) & 0x0F
        first = False
        offset += TS_PAYLOAD_SIZE

    return bytes(out), video_cc, pat_cc, pmt_cc


def frames_to_ts_segment(
    frames: list,
    base_pts_90khz: int = 0,
    frame_duration_90khz: int = 3000,
) -> bytes:
    """Convert a list of raw H.264 frame byte strings to a single .ts segment.

    Args:
        frames: Ordered list of H.264 Annex B byte strings, one per frame.
        base_pts_90khz: PTS for the first frame (default 0).
        frame_duration_90khz: PTS increment per frame (default 3000 = 1/30 s at 90 kHz).

    Returns:
        Complete MPEG-TS byte string suitable for writing to a .ts file.
    """
    out = bytearray()
    video_cc = pat_cc = pmt_cc = 0
    for i, frame in enumerate(frames):
        pts = (base_pts_90khz + i * frame_duration_90khz) & 0x1_FFFF_FFFF
        ts_data, video_cc, pat_cc, pmt_cc = mux_h264_to_ts(
            frame,
            pts,
            video_cc=video_cc,
            pat_cc=pat_cc,
            pmt_cc=pmt_cc,
            include_tables=(i == 0),
        )
        out.extend(ts_data)
    return bytes(out)
