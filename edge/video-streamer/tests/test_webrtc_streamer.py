"""
Unit tests for the WebRTC streaming pipeline (PEN-56 / M3-1).

Tests cover:
- WebRTCConfig defaults and custom values
- H264VideoStreamTrack: kind, PTS/timestamp progression, av.VideoFrame output
- WebRTCStreamer: peer connection lifecycle, DTLS/SRTP SDP negotiation,
  cleanup on close, H.264 codec preference
- FakeFrameSource contract (validates FrameSource ABC implementation)

Hardware (Picamera2) is never touched; FakeFrameSource provides deterministic
BGR frames for all tests.
"""

from __future__ import annotations

import asyncio
import fractions
from unittest.mock import AsyncMock, patch

import av
import numpy as np
import pytest
from aiortc import RTCPeerConnection

from config import StreamConfig
from webrtc_streamer import (
    FrameSource,
    H264VideoStreamTrack,
    WebRTCConfig,
    WebRTCStreamer,
)


# ---------------------------------------------------------------------------
# Helpers / test doubles
# ---------------------------------------------------------------------------


class FakeFrameSource(FrameSource):
    """Deterministic BGR frame source for tests.

    Returns zero-valued (black) frames of the configured size.
    Tracks call counts so tests can assert interaction behaviour.
    """

    def __init__(self, width: int = 64, height: int = 48) -> None:
        self._width = width
        self._height = height
        self._started = False
        self.get_frame_call_count = 0

    async def get_frame(self) -> np.ndarray:
        self.get_frame_call_count += 1
        return np.zeros((self._height, self._width, 3), dtype=np.uint8)

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    @property
    def started(self) -> bool:
        return self._started


def _make_stream_config(
    fps: int = 30,
    width: int = 64,
    height: int = 48,
) -> StreamConfig:
    return StreamConfig(
        width=width,
        height=height,
        fps=fps,
        bitrate=2_000_000,
        gop=30,
        profile="baseline",
    )


def _make_streamer(
    webrtc_config: WebRTCConfig | None = None,
    fps: int = 30,
) -> WebRTCStreamer:
    source = FakeFrameSource()
    config = _make_stream_config(fps=fps)
    return WebRTCStreamer(source, config, webrtc_config)


# ---------------------------------------------------------------------------
# WebRTCConfig
# ---------------------------------------------------------------------------


class TestWebRTCConfig:
    def test_default_stun_server_is_google(self) -> None:
        cfg = WebRTCConfig()
        assert len(cfg.stun_servers) == 1
        assert "stun.l.google.com" in cfg.stun_servers[0]

    def test_custom_stun_servers_stored(self) -> None:
        servers = ["stun:a.example.com:3478", "stun:b.example.com:3478"]
        cfg = WebRTCConfig(stun_servers=servers)
        assert cfg.stun_servers == servers

    def test_empty_stun_servers(self) -> None:
        cfg = WebRTCConfig(stun_servers=[])
        assert cfg.stun_servers == []

    def test_default_max_bitrate(self) -> None:
        assert WebRTCConfig().max_bitrate == 2_000_000

    def test_default_min_bitrate(self) -> None:
        assert WebRTCConfig().min_bitrate == 100_000

    def test_custom_bitrates(self) -> None:
        cfg = WebRTCConfig(max_bitrate=4_000_000, min_bitrate=200_000)
        assert cfg.max_bitrate == 4_000_000
        assert cfg.min_bitrate == 200_000

    def test_default_h264_profile(self) -> None:
        assert WebRTCConfig().h264_profile == "baseline"

    def test_custom_h264_profile(self) -> None:
        cfg = WebRTCConfig(h264_profile="main")
        assert cfg.h264_profile == "main"


# ---------------------------------------------------------------------------
# H264VideoStreamTrack
# ---------------------------------------------------------------------------


class TestH264VideoStreamTrack:
    def test_track_kind_is_video(self) -> None:
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config())
        assert track.kind == "video"

    def test_frame_source_property_returns_source(self) -> None:
        source = FakeFrameSource()
        track = H264VideoStreamTrack(source, _make_stream_config())
        assert track.frame_source is source

    def test_timestamp_initialised_to_zero(self) -> None:
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config())
        assert track._timestamp == 0

    def test_timestamp_increment_for_30fps(self) -> None:
        # 90 000 / 30 = 3 000
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config(fps=30))
        assert track._timestamp_increment == 3_000

    def test_timestamp_increment_for_25fps(self) -> None:
        # 90 000 / 25 = 3 600
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config(fps=25))
        assert track._timestamp_increment == 3_600

    def test_timestamp_increment_for_15fps(self) -> None:
        # 90 000 / 15 = 6 000
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config(fps=15))
        assert track._timestamp_increment == 6_000

    @pytest.mark.asyncio
    async def test_recv_returns_av_video_frame(self) -> None:
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config())
        with patch("asyncio.sleep", new_callable=AsyncMock):
            frame = await track.recv()
        assert isinstance(frame, av.VideoFrame)

    @pytest.mark.asyncio
    async def test_recv_calls_frame_source_once(self) -> None:
        source = FakeFrameSource()
        track = H264VideoStreamTrack(source, _make_stream_config())
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await track.recv()
        assert source.get_frame_call_count == 1

    @pytest.mark.asyncio
    async def test_recv_pts_starts_at_zero(self) -> None:
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config(fps=30))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            frame = await track.recv()
        assert frame.pts == 0

    @pytest.mark.asyncio
    async def test_recv_advances_pts_by_increment(self) -> None:
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config(fps=30))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            frame1 = await track.recv()
            frame2 = await track.recv()
        assert frame2.pts == frame1.pts + 3_000

    @pytest.mark.asyncio
    async def test_recv_pts_increments_monotonically(self) -> None:
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config(fps=30))
        pts_values: list[int] = []
        with patch("asyncio.sleep", new_callable=AsyncMock):
            for _ in range(5):
                frame = await track.recv()
                pts_values.append(frame.pts)
        # Each value should be strictly greater than the previous
        for a, b in zip(pts_values, pts_values[1:]):
            assert b > a

    @pytest.mark.asyncio
    async def test_recv_frame_time_base_is_90khz(self) -> None:
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config())
        with patch("asyncio.sleep", new_callable=AsyncMock):
            frame = await track.recv()
        assert frame.time_base == fractions.Fraction(1, 90_000)

    @pytest.mark.asyncio
    async def test_recv_frame_format_is_bgr24(self) -> None:
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config())
        with patch("asyncio.sleep", new_callable=AsyncMock):
            frame = await track.recv()
        assert frame.format.name == "bgr24"

    @pytest.mark.asyncio
    async def test_recv_sleeps_for_one_frame_period(self) -> None:
        fps = 10
        track = H264VideoStreamTrack(FakeFrameSource(), _make_stream_config(fps=fps))
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await track.recv()
        mock_sleep.assert_called_once_with(1.0 / fps)

    @pytest.mark.asyncio
    async def test_recv_multiple_calls_increment_source_counter(self) -> None:
        source = FakeFrameSource()
        track = H264VideoStreamTrack(source, _make_stream_config())
        with patch("asyncio.sleep", new_callable=AsyncMock):
            for _ in range(4):
                await track.recv()
        assert source.get_frame_call_count == 4


# ---------------------------------------------------------------------------
# WebRTCStreamer — unit tests (no real network)
# ---------------------------------------------------------------------------


class TestWebRTCStreamer:
    def test_initial_peer_connection_count_is_zero(self) -> None:
        streamer = _make_streamer()
        assert streamer.peer_connection_count == 0

    def test_build_rtc_configuration_single_stun(self) -> None:
        cfg = WebRTCConfig(stun_servers=["stun:my-stun.example.com:3478"])
        streamer = _make_streamer(cfg)
        rtc_cfg = streamer._build_rtc_configuration()
        assert len(rtc_cfg.iceServers) == 1
        assert rtc_cfg.iceServers[0].urls == ["stun:my-stun.example.com:3478"]

    def test_build_rtc_configuration_multiple_stun(self) -> None:
        cfg = WebRTCConfig(stun_servers=["stun:a:3478", "stun:b:3478"])
        streamer = _make_streamer(cfg)
        rtc_cfg = streamer._build_rtc_configuration()
        assert len(rtc_cfg.iceServers) == 2

    def test_build_rtc_configuration_empty_stun(self) -> None:
        cfg = WebRTCConfig(stun_servers=[])
        streamer = _make_streamer(cfg)
        rtc_cfg = streamer._build_rtc_configuration()
        assert rtc_cfg.iceServers == []

    def test_create_video_track_returns_h264_track(self) -> None:
        streamer = _make_streamer()
        track = streamer._create_video_track()
        assert isinstance(track, H264VideoStreamTrack)
        assert track.kind == "video"

    @pytest.mark.asyncio
    async def test_create_peer_connection_increments_count(self) -> None:
        streamer = _make_streamer()
        pc = await streamer.create_peer_connection()
        assert streamer.peer_connection_count == 1
        await pc.close()

    @pytest.mark.asyncio
    async def test_two_peer_connections_tracked(self) -> None:
        streamer = _make_streamer()
        pc1 = await streamer.create_peer_connection()
        pc2 = await streamer.create_peer_connection()
        assert streamer.peer_connection_count == 2
        await pc1.close()
        await pc2.close()

    @pytest.mark.asyncio
    async def test_close_all_clears_connections(self) -> None:
        streamer = _make_streamer()
        await streamer.create_peer_connection()
        await streamer.create_peer_connection()
        await streamer.close_all()
        assert streamer.peer_connection_count == 0

    @pytest.mark.asyncio
    async def test_close_all_idempotent_when_empty(self) -> None:
        streamer = _make_streamer()
        await streamer.close_all()  # should not raise
        assert streamer.peer_connection_count == 0

    @pytest.mark.asyncio
    async def test_connection_removed_after_manual_discard(self) -> None:
        """Verify that discarding a PC from the set updates the count."""
        streamer = _make_streamer()
        pc = await streamer.create_peer_connection()
        assert streamer.peer_connection_count == 1
        # Simulate the connectionstatechange handler removing the PC
        streamer._peer_connections.discard(pc)
        assert streamer.peer_connection_count == 0
        await pc.close()

    @pytest.mark.asyncio
    async def test_connection_removed_on_close_state(self) -> None:
        """Closing a PC should trigger removal via the state-change callback."""
        streamer = _make_streamer()
        pc = await streamer.create_peer_connection()
        assert streamer.peer_connection_count == 1

        await pc.close()
        # Allow the event loop to process the state-change callback
        await asyncio.sleep(0)

        assert streamer.peer_connection_count == 0

    @pytest.mark.asyncio
    async def test_peer_connection_has_video_transceiver(self) -> None:
        streamer = _make_streamer()
        pc = await streamer.create_peer_connection()
        transceivers = pc.getTransceivers()
        assert any(t.kind == "video" for t in transceivers)
        await pc.close()


# ---------------------------------------------------------------------------
# WebRTCStreamer — SDP / DTLS-SRTP integration tests
# ---------------------------------------------------------------------------


class TestWebRTCStreamerSDP:
    """Integration tests that exercise the real aiortc SDP offer/answer flow.

    No real network connections are made; aiortc generates the SDP in-process.
    Empty STUN server list keeps ICE gathering to host candidates only.
    """

    @pytest.mark.asyncio
    async def test_handle_offer_returns_string(self) -> None:
        streamer = _make_streamer(WebRTCConfig(stun_servers=[]))

        offerer = RTCPeerConnection()
        offerer.addTransceiver("video", direction="recvonly")
        offer = await offerer.createOffer()
        await offerer.setLocalDescription(offer)

        answer_sdp = await streamer.handle_offer(offerer.localDescription.sdp)

        assert isinstance(answer_sdp, str)
        assert len(answer_sdp) > 0

        await offerer.close()
        await streamer.close_all()

    @pytest.mark.asyncio
    async def test_handle_offer_sdp_is_answer_type(self) -> None:
        """The SDP returned must begin with a standard session header."""
        streamer = _make_streamer(WebRTCConfig(stun_servers=[]))

        offerer = RTCPeerConnection()
        offerer.addTransceiver("video", direction="recvonly")
        offer = await offerer.createOffer()
        await offerer.setLocalDescription(offer)

        answer_sdp = await streamer.handle_offer(offerer.localDescription.sdp)

        # Standard SDP session header
        assert "v=0" in answer_sdp

        await offerer.close()
        await streamer.close_all()

    @pytest.mark.asyncio
    async def test_handle_offer_sdp_contains_video_media(self) -> None:
        streamer = _make_streamer(WebRTCConfig(stun_servers=[]))

        offerer = RTCPeerConnection()
        offerer.addTransceiver("video", direction="recvonly")
        offer = await offerer.createOffer()
        await offerer.setLocalDescription(offer)

        answer_sdp = await streamer.handle_offer(offerer.localDescription.sdp)

        assert "m=video" in answer_sdp

        await offerer.close()
        await streamer.close_all()

    @pytest.mark.asyncio
    async def test_handle_offer_sdp_contains_dtls_fingerprint(self) -> None:
        """DTLS/SRTP requires a certificate fingerprint attribute in SDP."""
        streamer = _make_streamer(WebRTCConfig(stun_servers=[]))

        offerer = RTCPeerConnection()
        offerer.addTransceiver("video", direction="recvonly")
        offer = await offerer.createOffer()
        await offerer.setLocalDescription(offer)

        answer_sdp = await streamer.handle_offer(offerer.localDescription.sdp)

        # a=fingerprint:<hash-func> <fingerprint-value>  proves DTLS is negotiated
        assert "a=fingerprint:" in answer_sdp

        await offerer.close()
        await streamer.close_all()

    @pytest.mark.asyncio
    async def test_handle_offer_sdp_contains_srtp_setup_attribute(self) -> None:
        """a=setup: attribute drives DTLS role (actpass/passive/active)."""
        streamer = _make_streamer(WebRTCConfig(stun_servers=[]))

        offerer = RTCPeerConnection()
        offerer.addTransceiver("video", direction="recvonly")
        offer = await offerer.createOffer()
        await offerer.setLocalDescription(offer)

        answer_sdp = await streamer.handle_offer(offerer.localDescription.sdp)

        assert "a=setup:" in answer_sdp

        await offerer.close()
        await streamer.close_all()

    @pytest.mark.asyncio
    async def test_handle_offer_creates_peer_connection(self) -> None:
        streamer = _make_streamer(WebRTCConfig(stun_servers=[]))
        assert streamer.peer_connection_count == 0

        offerer = RTCPeerConnection()
        offerer.addTransceiver("video", direction="recvonly")
        offer = await offerer.createOffer()
        await offerer.setLocalDescription(offer)

        await streamer.handle_offer(offerer.localDescription.sdp)

        assert streamer.peer_connection_count == 1

        await offerer.close()
        await streamer.close_all()

    @pytest.mark.asyncio
    async def test_handle_offer_multiple_clients(self) -> None:
        """Each call to handle_offer produces a distinct peer connection."""
        streamer = _make_streamer(WebRTCConfig(stun_servers=[]))

        async def make_offerer() -> RTCPeerConnection:
            pc = RTCPeerConnection()
            pc.addTransceiver("video", direction="recvonly")
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            return pc

        offerer1 = await make_offerer()
        offerer2 = await make_offerer()

        await streamer.handle_offer(offerer1.localDescription.sdp)
        await streamer.handle_offer(offerer2.localDescription.sdp)

        assert streamer.peer_connection_count == 2

        await offerer1.close()
        await offerer2.close()
        await streamer.close_all()

    @pytest.mark.asyncio
    async def test_handle_offer_sdp_contains_h264_codec(self) -> None:
        """The answer SDP must advertise H.264 as a supported codec."""
        streamer = _make_streamer(WebRTCConfig(stun_servers=[]))

        offerer = RTCPeerConnection()
        offerer.addTransceiver("video", direction="recvonly")
        offer = await offerer.createOffer()
        await offerer.setLocalDescription(offer)

        answer_sdp = await streamer.handle_offer(offerer.localDescription.sdp)

        assert "H264" in answer_sdp or "h264" in answer_sdp.lower()

        await offerer.close()
        await streamer.close_all()


# ---------------------------------------------------------------------------
# FakeFrameSource (validates FrameSource ABC contract)
# ---------------------------------------------------------------------------


class TestFakeFrameSource:
    def test_initial_started_state_is_false(self) -> None:
        source = FakeFrameSource()
        assert not source.started

    def test_start_sets_started_true(self) -> None:
        source = FakeFrameSource()
        source.start()
        assert source.started

    def test_stop_sets_started_false(self) -> None:
        source = FakeFrameSource()
        source.start()
        source.stop()
        assert not source.started

    def test_is_frame_source_subclass(self) -> None:
        assert issubclass(FakeFrameSource, FrameSource)

    @pytest.mark.asyncio
    async def test_get_frame_returns_correct_shape(self) -> None:
        source = FakeFrameSource(width=32, height=24)
        frame = await source.get_frame()
        assert frame.shape == (24, 32, 3)

    @pytest.mark.asyncio
    async def test_get_frame_returns_uint8(self) -> None:
        source = FakeFrameSource()
        frame = await source.get_frame()
        assert frame.dtype == np.uint8

    @pytest.mark.asyncio
    async def test_get_frame_increments_counter(self) -> None:
        source = FakeFrameSource()
        await source.get_frame()
        await source.get_frame()
        await source.get_frame()
        assert source.get_frame_call_count == 3
