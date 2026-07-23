"""
Telemetry emitter for the Raspberry Pi video streamer.

Emits ``video_stream_start``, ``video_stream_stop``, and
``video_stream_health`` events to the Wrack unified telemetry ingress.

Sending is delegated to the shared Raspberry Pi telemetry module
(``edge/vision/telemetry/``, PEN-166) via ``RpiTelemetryCollector`` +
``RpiTelemetrySender``, which gives this class retry/backoff, HTTP 207
partial-failure handling, and disk-overflow buffering (PEN-216) -- none of
which the original inline ``urllib`` implementation had.

Usage::

    from video_telemetry import VideoTelemetry

    tel = VideoTelemetry(
        endpoint_url="https://.../unifiedIngress",
        api_key="your-per-device-token",
        device_id="rpi-camera-01",
        telemetry_enabled=True,   # off by default
    )

    tel.emit_stream_start(protocol="udp", port=9999,
                          resolution_width=1280, resolution_height=720,
                          target_fps=30)

    # ... on each 10-s status tick ...
    tel.emit_stream_health(fps_recent=29.5, client_count=2,
                           frame_drop_total=3, uptime_seconds=60.0)

    tel.emit_stream_stop(reason="keyboard_interrupt",
                         uptime_seconds=60.0, total_frames_sent=1800,
                         total_frame_drops=3)

Endpoint and auth
------------------
``endpoint_url`` must be the ``unifiedIngress`` Cloud Function URL
(PEN-227), and ``api_key`` must be a per-device token provisioned via
``cloud/functions/setup-device-tokens.sh`` -- the legacy shared
``telemetryIngestion`` endpoint and static ``X-API-Key`` are no longer
accepted by the ingress this module targets.

Module naming
-------------
This file was named ``telemetry.py`` prior to PEN-216. It was renamed to
``video_telemetry.py`` so that it can import the ``edge/vision/telemetry``
package (also named ``telemetry``) unambiguously -- two top-level modules
cannot both be named ``telemetry`` in the same Python process.
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
import threading
import uuid
from typing import Any, Dict, Optional

# edge/vision/ (sibling of edge/video-streamer/) hosts the shared RPi
# telemetry module (PEN-166). Add it to sys.path so it can be imported as a
# plain top-level `telemetry` package -- safe now that this file is no
# longer itself named telemetry.py (see "Module naming" above).
_VISION_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vision"
)
if _VISION_ROOT not in sys.path:
    sys.path.insert(0, _VISION_ROOT)

from telemetry.collector import RpiTelemetryCollector  # noqa: E402
from telemetry.sender import RpiTelemetrySender  # noqa: E402

LOGGER = logging.getLogger("streamer.telemetry")

_SOURCE = "rpi"
_VERSION = "1.0"


class VideoTelemetry:
    """Fire-and-forget telemetry emitter for the video streamer.

    All ``emit_*`` methods return immediately; the send happens in a
    daemon background thread so it never blocks the streaming loop.

    Parameters
    ----------
    endpoint_url:
        Full URL of the ``unifiedIngress`` Cloud Function (PEN-227).
    api_key:
        Per-device token to pass as the ``X-Device-Token`` request header
        (provision with ``cloud/functions/setup-device-tokens.sh``).
    device_id:
        Identifier for this Raspberry Pi (e.g. ``"rpi-camera-01"``).
    session_id:
        Optional session UUID to group related events. If *None*, a new
        UUID is generated when the first event is emitted.
    telemetry_enabled:
        When *False* (the default) all ``emit_*`` calls are no-ops.
        Set to *True* to actually send events.
    timeout_seconds:
        HTTP request timeout in seconds (default: 5).
    """

    def __init__(
        self,
        endpoint_url: str = "",
        api_key: str = "",
        device_id: str = "rpi-camera-01",
        session_id: Optional[str] = None,
        telemetry_enabled: bool = False,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.device_id = device_id
        self.session_id = session_id or str(uuid.uuid4())
        self.telemetry_enabled = telemetry_enabled
        self.timeout_seconds = timeout_seconds

        # Shared across all emit_* calls on this instance so that events
        # unsent after a failed flush (see RpiTelemetrySender.flush_and_send)
        # are re-buffered here and retried on the next emit, rather than
        # being silently lost. Schema validation is left off: this class
        # builds its own envelope (with a `version` field the shared module
        # doesn't produce) and is responsible for its own payload shape.
        self._collector = RpiTelemetryCollector(
            source=_SOURCE,
            device_id=self.device_id,
            session_id=self.session_id,
            validate=False,
        )
        self._sender: Optional[RpiTelemetrySender] = None
        self._send_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public emit methods
    # ------------------------------------------------------------------

    def emit_stream_start(
        self,
        protocol: str,
        port: int,
        resolution_width: int,
        resolution_height: int,
        target_fps: float,
        bitrate: Optional[int] = None,
    ) -> None:
        """Emit a ``video_stream_start`` event."""
        payload: Dict[str, Any] = {
            "protocol": protocol,
            "port": port,
            "resolution_width": resolution_width,
            "resolution_height": resolution_height,
            "target_fps": target_fps,
        }
        if bitrate is not None:
            payload["bitrate"] = bitrate

        self._emit("video_stream_start", payload)

    def emit_stream_stop(
        self,
        reason: str,
        uptime_seconds: Optional[float] = None,
        total_frames_sent: Optional[int] = None,
        total_frame_drops: Optional[int] = None,
    ) -> None:
        """Emit a ``video_stream_stop`` event.

        Unlike other emit methods this call blocks up to ``timeout_seconds``
        while waiting for the send to complete. This prevents the event
        from being dropped when the Python process exits immediately after
        ``stop()`` returns (daemon threads are killed at interpreter shutdown).
        """
        payload: Dict[str, Any] = {"reason": reason}
        if uptime_seconds is not None:
            payload["uptime_seconds"] = uptime_seconds
        if total_frames_sent is not None:
            payload["total_frames_sent"] = total_frames_sent
        if total_frame_drops is not None:
            payload["total_frame_drops"] = total_frame_drops

        self._emit_blocking("video_stream_stop", payload)

    def emit_stream_health(
        self,
        fps_recent: float,
        client_count: int,
        frame_drop_total: int,
        uptime_seconds: float,
        interval_seconds: Optional[float] = None,
    ) -> None:
        """Emit a ``video_stream_health`` event (called each status tick)."""
        payload: Dict[str, Any] = {
            "fps_recent": fps_recent,
            "client_count": client_count,
            "frame_drop_total": frame_drop_total,
            "uptime_seconds": uptime_seconds,
        }
        if interval_seconds is not None:
            payload["interval_seconds"] = interval_seconds

        self._emit("video_stream_health", payload)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Build the event envelope and dispatch via a background daemon thread."""
        if not self.telemetry_enabled:
            return
        self._start_send_thread(event_type, payload, daemon=True)

    def _emit_blocking(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Build the event envelope and dispatch via a non-daemon thread, then
        join with ``timeout_seconds``.

        Used for lifecycle-critical events (e.g. ``video_stream_stop``) where
        the process may exit immediately after this call. Non-daemon threads
        are waited on by the Python interpreter at shutdown, so joining with a
        timeout ensures the send is not killed mid-flight.
        """
        if not self.telemetry_enabled:
            return
        t = self._start_send_thread(event_type, payload, daemon=False)
        t.join(timeout=self.timeout_seconds)

    def _start_send_thread(
        self, event_type: str, payload: Dict[str, Any], *, daemon: bool
    ) -> threading.Thread:
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "source": _SOURCE,
            "timestamp": _utc_now_iso(),
            "device_id": self.device_id,
            "session_id": self.session_id,
            "version": _VERSION,
            "payload": payload,
        }
        t = threading.Thread(
            target=self._post_async,
            args=(event,),
            daemon=daemon,
            name=f"telemetry-{event_type}",
        )
        t.start()
        return t

    def _get_sender(self) -> Optional[RpiTelemetrySender]:
        """Lazily construct the shared RPi telemetry sender.

        Deferred until first use because ``RpiTelemetrySender`` raises
        ``ValueError`` when constructed with an empty endpoint, and
        ``VideoTelemetry``'s default ``endpoint_url=""`` must remain a
        silent no-op (checked by the caller before this is invoked).
        """
        if self._sender is None:
            self._sender = RpiTelemetrySender(
                endpoint=self.endpoint_url,
                device_id=self.device_id,
                device_token=self.api_key,
                timeout=self.timeout_seconds,
            )
        return self._sender

    def _post_async(self, event: Dict[str, Any]) -> None:
        """Buffer *event* and hand it off to the shared RPi telemetry sender.

        Runs in a background thread (see ``_start_send_thread``). Delegates
        the actual send to ``RpiTelemetryCollector``/``RpiTelemetrySender``
        (PEN-166) for retry/backoff, HTTP 207 partial-failure handling, and
        disk-overflow buffering.
        """
        if not self.endpoint_url:
            LOGGER.warning(
                "telemetry: endpoint_url is empty; event %s dropped",
                event.get("event_id"),
            )
            return

        try:
            sender = self._get_sender()
            with self._send_lock:
                self._collector.collect_raw(event)
                sender.flush_and_send(self._collector, async_send=False)
        except Exception as exc:  # noqa: BLE001 - fire-and-forget, must never raise
            LOGGER.warning(
                "telemetry: unexpected error sending %s: %s",
                event.get("event_type"),
                exc,
            )


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string ending in ``Z``."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
