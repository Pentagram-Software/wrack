"""
WebRTC streaming pipeline for Raspberry Pi (PEN-56 / M3-1).

Implements an RTP/SRTP/DTLS media pipeline using aiortc.
DTLS key exchange and SRTP media encryption are handled automatically by the
aiortc library; this module wires the H.264 video track into an
RTCPeerConnection and manages the SDP offer/answer handshake.

Design decisions:
- FrameSource ABC decouples the camera from the WebRTC track, enabling DI
  and straightforward unit testing without Pi hardware.
- H264VideoStreamTrack exposes a standard aiortc MediaStreamTrack whose
  recv() drives the RTP clock (90 kHz) and frame pacing.
- WebRTCStreamer is stateless with respect to individual connections; it
  creates, tracks, and tears down RTCPeerConnections on demand.
- H.264 is promoted to first codec preference when supported by aiortc so
  that the SDP answer always negotiates H264/SRTP.
"""

from __future__ import annotations

import asyncio
import fractions
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import av
import numpy as np
from aiortc import (
    MediaStreamTrack,
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)

from config import StreamConfig

LOGGER = logging.getLogger("webrtc_streamer")

# Standard RTP clock rate for video (90 kHz per RFC 3551)
RTP_VIDEO_CLOCK_RATE = 90_000


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class WebRTCConfig:
    """Runtime configuration for the WebRTC pipeline.

    Attributes:
        stun_servers: STUN server URIs used for ICE candidate gathering.
        h264_profile: Preferred H.264 profile advertised in SDP.
        max_bitrate: Upper bound for the video encoder bit-rate (bps).
        min_bitrate: Lower bound for the video encoder bit-rate (bps).
    """

    stun_servers: list[str] = field(
        default_factory=lambda: ["stun:stun.l.google.com:19302"]
    )
    h264_profile: str = "baseline"
    max_bitrate: int = 2_000_000
    min_bitrate: int = 100_000


# ---------------------------------------------------------------------------
# Frame source abstraction
# ---------------------------------------------------------------------------


class FrameSource(ABC):
    """Abstract interface for video frame providers.

    Implementations supply raw BGR frames to the WebRTC track.  The
    abstraction makes it possible to swap in mock sources for unit tests
    or alternative hardware backends without changing the pipeline.
    """

    @abstractmethod
    async def get_frame(self) -> np.ndarray:
        """Return the next video frame as a BGR numpy array (H×W×3, uint8)."""

    @abstractmethod
    def start(self) -> None:
        """Prepare and activate the frame source."""

    @abstractmethod
    def stop(self) -> None:
        """Deactivate and release the frame source."""


# ---------------------------------------------------------------------------
# Hardware frame source (Pi only — guarded import)
# ---------------------------------------------------------------------------


try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder

    class Picamera2FrameSource(FrameSource):
        """Frame source backed by a real Raspberry Pi camera via Picamera2.

        Not used in unit tests — instantiating this class requires Pi hardware
        with a connected camera module.
        """

        def __init__(self, config: StreamConfig) -> None:
            self._config = config
            self._camera: Optional[Picamera2] = None
            self._encoder: Optional[H264Encoder] = None

        def start(self) -> None:
            self._camera = Picamera2()
            cam_cfg = self._camera.create_video_configuration(
                main={"size": self._config.resolution, "format": "RGB888"}
            )
            self._camera.configure(cam_cfg)
            self._encoder = H264Encoder(
                bitrate=self._config.bitrate,
                profile=self._config.profile,
                intra_period=self._config.gop,
            )
            self._camera.start()

        def stop(self) -> None:
            if self._camera is not None:
                self._camera.stop()
                self._camera = None

        async def get_frame(self) -> np.ndarray:
            if self._camera is None:
                raise RuntimeError("Picamera2FrameSource not started")
            import cv2

            frame = self._camera.capture_array()
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

except ImportError:
    # Picamera2 is not available outside the Raspberry Pi environment.
    pass


# ---------------------------------------------------------------------------
# WebRTC video track
# ---------------------------------------------------------------------------


class H264VideoStreamTrack(MediaStreamTrack):
    """aiortc MediaStreamTrack that delivers BGR frames as H.264 over RTP.

    aiortc re-encodes the returned av.VideoFrame objects to H.264 and
    packetises them into RTP.  SRTP encryption and DTLS key exchange are
    applied automatically by the RTCPeerConnection that owns this track.

    The RTP presentation timestamps (PTS) are driven by the standard 90 kHz
    video clock, paced to the configured frame rate.
    """

    kind = "video"

    def __init__(self, source: FrameSource, config: StreamConfig) -> None:
        super().__init__()
        self._source = source
        self._config = config
        self._timestamp: int = 0
        self._timestamp_increment: int = RTP_VIDEO_CLOCK_RATE // max(config.fps, 1)

    @property
    def frame_source(self) -> FrameSource:
        """The underlying FrameSource that supplies raw BGR frames."""
        return self._source

    async def recv(self) -> av.VideoFrame:
        """Return the next paced video frame for RTP delivery.

        The method sleeps for one frame period to enforce the configured
        frame rate, then fetches a BGR frame from the source and wraps it
        in an av.VideoFrame with the correct PTS and time base.
        """
        await asyncio.sleep(1.0 / max(self._config.fps, 1))

        frame_array = await self._source.get_frame()

        video_frame = av.VideoFrame.from_ndarray(frame_array, format="bgr24")
        video_frame.pts = self._timestamp
        video_frame.time_base = fractions.Fraction(1, RTP_VIDEO_CLOCK_RATE)

        self._timestamp += self._timestamp_increment
        return video_frame


# ---------------------------------------------------------------------------
# WebRTC pipeline / peer connection manager
# ---------------------------------------------------------------------------


class WebRTCStreamer:
    """WebRTC streaming pipeline.

    Creates and manages RTCPeerConnections, each of which carries an H.264
    video track encrypted with SRTP (negotiated via DTLS-SRTP as mandated by
    RFC 5763 / RFC 5764).  All DTLS/SRTP plumbing is handled by aiortc.

    Usage pattern
    -------------
    1. Receive a WebRTC SDP offer from a browser (via a signaling channel).
    2. Call ``handle_offer(sdp_offer)`` → returns the SDP answer.
    3. Exchange the answer back over the signaling channel.
    4. ICE connectivity checks proceed automatically.

    Each RTCPeerConnection is automatically removed from the internal set when
    its state transitions to "failed" or "closed".
    """

    def __init__(
        self,
        frame_source: FrameSource,
        stream_config: StreamConfig,
        webrtc_config: Optional[WebRTCConfig] = None,
    ) -> None:
        self._frame_source = frame_source
        self._stream_config = stream_config
        self._webrtc_config = webrtc_config or WebRTCConfig()
        self._peer_connections: set[RTCPeerConnection] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def peer_connection_count(self) -> int:
        """Number of currently active peer connections."""
        return len(self._peer_connections)

    async def handle_offer(self, sdp_offer: str) -> str:
        """Process a WebRTC SDP offer and return the SDP answer.

        Creates a new RTCPeerConnection with an H.264 video track, applies
        the remote offer, generates a local answer, and returns the answer
        SDP string.  DTLS certificate fingerprints are embedded in the SDP
        answer by aiortc, proving SRTP will be used for media.

        Args:
            sdp_offer: The SDP offer string received from the browser/client.

        Returns:
            The SDP answer string to be sent back to the browser/client.
        """
        pc = await self.create_peer_connection()

        offer = RTCSessionDescription(sdp=sdp_offer, type="offer")
        await pc.setRemoteDescription(offer)

        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        LOGGER.info("Produced SDP answer for new peer connection")
        return pc.localDescription.sdp

    async def create_peer_connection(self) -> RTCPeerConnection:
        """Create and register a new RTCPeerConnection with an H.264 video track.

        The connection is automatically removed from the internal set when it
        transitions to a terminal state (``failed`` or ``closed``).
        """
        pc = RTCPeerConnection(configuration=self._build_rtc_configuration())
        self._peer_connections.add(pc)

        @pc.on("connectionstatechange")
        async def on_connection_state_change() -> None:
            LOGGER.info(
                "Peer connection state: %s (total=%d)",
                pc.connectionState,
                len(self._peer_connections),
            )
            if pc.connectionState in ("failed", "closed"):
                self._peer_connections.discard(pc)
                LOGGER.info(
                    "Removed peer connection (state=%s, remaining=%d)",
                    pc.connectionState,
                    len(self._peer_connections),
                )

        track = self._create_video_track()
        pc.addTrack(track)

        self._prefer_h264(pc)

        return pc

    async def close_all(self) -> None:
        """Close all active peer connections and clear the internal set."""
        for pc in list(self._peer_connections):
            await pc.close()
        self._peer_connections.clear()
        LOGGER.info("All peer connections closed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_rtc_configuration(self) -> RTCConfiguration:
        """Build an RTCConfiguration from the current WebRTCConfig."""
        ice_servers = [
            RTCIceServer(urls=[url]) for url in self._webrtc_config.stun_servers
        ]
        return RTCConfiguration(iceServers=ice_servers)

    def _create_video_track(self) -> H264VideoStreamTrack:
        return H264VideoStreamTrack(self._frame_source, self._stream_config)

    @staticmethod
    def _prefer_h264(pc: RTCPeerConnection) -> None:
        """Reorder transceiver codec preferences to place H.264 first.

        This is a best-effort operation — if aiortc does not expose H.264
        capabilities (e.g. in a stripped build), the method logs a warning
        and leaves codec preferences unchanged.
        """
        try:
            from aiortc import RTCRtpSender

            capabilities = RTCRtpSender.getCapabilities("video")
            if capabilities is None:
                return

            h264_codecs = [
                c for c in capabilities.codecs if "H264" in c.mimeType.upper()
            ]
            other_codecs = [
                c for c in capabilities.codecs if "H264" not in c.mimeType.upper()
            ]
            preferred = h264_codecs + other_codecs

            for transceiver in pc.getTransceivers():
                if transceiver.kind == "video":
                    transceiver.setCodecPreferences(preferred)

        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not set H264 codec preference: %s", exc)
