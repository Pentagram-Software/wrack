"""
Minimal telemetry emitter for the Raspberry Pi video streamer.

Emits ``video_stream_start``, ``video_stream_stop``, and
``video_stream_health`` events to the Wrack telemetryIngestion Cloud
Function via fire-and-forget HTTP POST.

This module intentionally mirrors the architecture of
``robot/controller/telemetry/`` but is simplified for standard CPython
running on a Raspberry Pi (no MicroPython constraints).

Usage::

    from telemetry import VideoTelemetry

    tel = VideoTelemetry(
        endpoint_url="https://.../telemetryIngestion",
        api_key="your-key",
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

BigQuery dependency
-------------------
Events are sent to the ``telemetryIngestion`` Cloud Function (see
``cloud/functions/telemetry.js``), which batch-inserts them into the
``wrack_telemetry.events`` BigQuery table.

PEN-166 note
------------
Once the dedicated RPi telemetry module (PEN-166) is implemented, its
``TelemetryCollector`` + ``TelemetrySender`` can replace the HTTP call
inside ``_post_async`` with no changes to the public API of this class.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
import uuid
from typing import Any, Dict, Optional
from urllib import request as urllib_request
from urllib.error import URLError

LOGGER = logging.getLogger("streamer.telemetry")

_SOURCE = "rpi"
_VERSION = "1.0"


class VideoTelemetry:
    """Fire-and-forget telemetry emitter for the video streamer.

    All ``emit_*`` methods return immediately; the HTTP POST happens in a
    daemon background thread so it never blocks the streaming loop.

    Parameters
    ----------
    endpoint_url:
        Full URL of the ``telemetryIngestion`` Cloud Function.
    api_key:
        Value to pass as the ``X-API-Key`` request header.
    device_id:
        Identifier for this Raspberry Pi (e.g. ``"rpi-camera-01"``).
    session_id:
        Optional session UUID to group related events.  If *None*, a new
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
        while waiting for the HTTP POST to complete.  This prevents the event
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
        the process may exit immediately after this call.  Non-daemon threads
        are waited on by the Python interpreter at shutdown, so joining with a
        timeout ensures the HTTP POST is not killed mid-flight.
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

    def _post_async(self, event: Dict[str, Any]) -> None:
        """Perform the HTTP POST in a background thread (fire-and-forget)."""
        if not self.endpoint_url:
            LOGGER.warning(
                "telemetry: endpoint_url is empty; event %s dropped",
                event.get("event_id"),
            )
            return

        body = json.dumps({"events": [event]}).encode("utf-8")
        req = urllib_request.Request(
            self.endpoint_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as resp:
                status = resp.status
                if status not in (200, 207):
                    LOGGER.warning(
                        "telemetry: unexpected HTTP %s for event %s",
                        status,
                        event.get("event_id"),
                    )
        except URLError as exc:
            LOGGER.warning(
                "telemetry: failed to send %s event: %s",
                event.get("event_type"),
                exc,
            )
        except Exception as exc:  # pragma: no cover
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
