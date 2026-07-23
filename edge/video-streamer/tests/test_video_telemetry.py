"""
Unit tests for edge/video-streamer/video_telemetry.py.

All sends are mocked at the RpiTelemetrySender boundary (edge/vision/telemetry,
PEN-166) so no real network requests are made.
"""

import threading
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

from video_telemetry import VideoTelemetry, _utc_now_iso


# ---------------------------------------------------------------------------
# _utc_now_iso helper
# ---------------------------------------------------------------------------

class TestUtcNowIso:
    def test_format_is_iso8601_with_z(self):
        import re
        ts = _utc_now_iso()
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z$", ts)

    def test_ends_with_z(self):
        assert _utc_now_iso().endswith("Z")

    def test_returns_string(self):
        assert isinstance(_utc_now_iso(), str)


# ---------------------------------------------------------------------------
# VideoTelemetry — construction
# ---------------------------------------------------------------------------

class TestVideoTelemetryConstruction:
    def test_telemetry_disabled_by_default(self):
        tel = VideoTelemetry()
        assert tel.telemetry_enabled is False

    def test_custom_device_id(self):
        tel = VideoTelemetry(device_id="rpi-test-99")
        assert tel.device_id == "rpi-test-99"

    def test_session_id_auto_generated(self):
        import re
        tel = VideoTelemetry()
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            tel.session_id,
            re.IGNORECASE,
        )

    def test_custom_session_id(self):
        tel = VideoTelemetry(session_id="my-session")
        assert tel.session_id == "my-session"

    def test_endpoint_and_api_key_stored(self):
        tel = VideoTelemetry(endpoint_url="https://example.com/fn", api_key="secret")
        assert tel.endpoint_url == "https://example.com/fn"
        assert tel.api_key == "secret"

    def test_timeout_default(self):
        tel = VideoTelemetry()
        assert tel.timeout_seconds == 5.0

    def test_custom_timeout(self):
        tel = VideoTelemetry(timeout_seconds=10.0)
        assert tel.timeout_seconds == 10.0


# ---------------------------------------------------------------------------
# No-op when telemetry_enabled=False
# ---------------------------------------------------------------------------

class TestTelemetryDisabled:
    def _make_disabled(self):
        return VideoTelemetry(
            endpoint_url="https://example.com/telemetry",
            api_key="key",
            telemetry_enabled=False,
        )

    def test_emit_start_does_not_call_post(self):
        tel = self._make_disabled()
        with patch.object(tel, "_post_async") as mock_post:
            tel.emit_stream_start("udp", 9999, 1280, 720, 30.0)
            mock_post.assert_not_called()

    def test_emit_stop_does_not_call_post(self):
        tel = self._make_disabled()
        with patch.object(tel, "_post_async") as mock_post:
            tel.emit_stream_stop("keyboard_interrupt")
            mock_post.assert_not_called()

    def test_emit_health_does_not_call_post(self):
        tel = self._make_disabled()
        with patch.object(tel, "_post_async") as mock_post:
            tel.emit_stream_health(29.5, 2, 3, 120.0)
            mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Event envelope structure
# ---------------------------------------------------------------------------

class TestEventEnvelope:
    def _capture_event(self, tel: VideoTelemetry, emit_fn, *args, **kwargs):
        """Call emit_fn and capture the event passed to _post_async."""
        captured = {}

        def fake_post(event):
            captured["event"] = event

        with patch.object(tel, "_post_async", side_effect=fake_post):
            emit_fn(*args, **kwargs)

        return captured.get("event")

    def _make_enabled(self, **kwargs):
        return VideoTelemetry(
            endpoint_url="https://example.com/tel",
            api_key="k",
            telemetry_enabled=True,
            **kwargs,
        )

    def test_stream_start_event_type(self):
        tel = self._make_enabled()
        event = self._capture_event(
            tel, tel.emit_stream_start, "udp", 9999, 1280, 720, 30.0
        )
        assert event["event_type"] == "video_stream_start"

    def test_stream_stop_event_type(self):
        tel = self._make_enabled()
        event = self._capture_event(tel, tel.emit_stream_stop, "keyboard_interrupt")
        assert event["event_type"] == "video_stream_stop"

    def test_stream_health_event_type(self):
        tel = self._make_enabled()
        event = self._capture_event(
            tel, tel.emit_stream_health, 29.5, 2, 3, 120.0
        )
        assert event["event_type"] == "video_stream_health"

    def test_source_is_rpi(self):
        tel = self._make_enabled()
        event = self._capture_event(tel, tel.emit_stream_stop, "stop_called")
        assert event["source"] == "rpi"

    def test_event_id_is_uuid(self):
        import re
        tel = self._make_enabled()
        event = self._capture_event(tel, tel.emit_stream_stop, "stop_called")
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            event["event_id"],
            re.IGNORECASE,
        )

    def test_timestamp_is_iso8601(self):
        import re
        tel = self._make_enabled()
        event = self._capture_event(tel, tel.emit_stream_stop, "stop_called")
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z$",
            event["timestamp"],
        )

    def test_device_id_in_envelope(self):
        tel = self._make_enabled(device_id="rpi-test-01")
        event = self._capture_event(tel, tel.emit_stream_stop, "stop_called")
        assert event["device_id"] == "rpi-test-01"

    def test_session_id_in_envelope(self):
        tel = self._make_enabled(session_id="sess-123")
        event = self._capture_event(tel, tel.emit_stream_stop, "stop_called")
        assert event["session_id"] == "sess-123"

    def test_payload_is_dict(self):
        tel = self._make_enabled()
        event = self._capture_event(tel, tel.emit_stream_stop, "stop_called")
        assert isinstance(event["payload"], dict)


# ---------------------------------------------------------------------------
# Payload contents
# ---------------------------------------------------------------------------

class TestPayloadContents:
    def _make_enabled(self):
        return VideoTelemetry(
            endpoint_url="https://example.com/tel",
            api_key="k",
            telemetry_enabled=True,
        )

    def _capture_payload(self, tel, emit_fn, *args, **kwargs):
        captured = {}

        def fake_post(event):
            captured["event"] = event

        with patch.object(tel, "_post_async", side_effect=fake_post):
            emit_fn(*args, **kwargs)

        return captured["event"]["payload"]

    def test_stream_start_payload_fields(self):
        tel = self._make_enabled()
        payload = self._capture_payload(
            tel, tel.emit_stream_start, "udp", 9999, 1280, 720, 30.0, bitrate=2_000_000
        )
        assert payload["protocol"] == "udp"
        assert payload["port"] == 9999
        assert payload["resolution_width"] == 1280
        assert payload["resolution_height"] == 720
        assert payload["target_fps"] == 30.0
        assert payload["bitrate"] == 2_000_000

    def test_stream_start_bitrate_optional(self):
        tel = self._make_enabled()
        payload = self._capture_payload(
            tel, tel.emit_stream_start, "udp", 9999, 640, 480, 25.0
        )
        assert "bitrate" not in payload

    def test_stream_stop_payload_reason(self):
        tel = self._make_enabled()
        payload = self._capture_payload(tel, tel.emit_stream_stop, "error")
        assert payload["reason"] == "error"

    def test_stream_stop_optional_fields(self):
        tel = self._make_enabled()
        payload = self._capture_payload(
            tel,
            tel.emit_stream_stop,
            "keyboard_interrupt",
            uptime_seconds=300.0,
            total_frames_sent=9000,
            total_frame_drops=5,
        )
        assert payload["uptime_seconds"] == pytest.approx(300.0)
        assert payload["total_frames_sent"] == 9000
        assert payload["total_frame_drops"] == 5

    def test_stream_stop_optional_fields_absent_when_none(self):
        tel = self._make_enabled()
        payload = self._capture_payload(tel, tel.emit_stream_stop, "stop_called")
        assert "uptime_seconds" not in payload
        assert "total_frames_sent" not in payload
        assert "total_frame_drops" not in payload

    def test_stream_health_payload_fields(self):
        tel = self._make_enabled()
        payload = self._capture_payload(
            tel,
            tel.emit_stream_health,
            fps_recent=28.7,
            client_count=3,
            frame_drop_total=2,
            uptime_seconds=600.0,
            interval_seconds=10.0,
        )
        assert payload["fps_recent"] == pytest.approx(28.7)
        assert payload["client_count"] == 3
        assert payload["frame_drop_total"] == 2
        assert payload["uptime_seconds"] == pytest.approx(600.0)
        assert payload["interval_seconds"] == pytest.approx(10.0)

    def test_stream_health_interval_optional(self):
        tel = self._make_enabled()
        payload = self._capture_payload(
            tel, tel.emit_stream_health, 30.0, 1, 0, 60.0
        )
        assert "interval_seconds" not in payload


# ---------------------------------------------------------------------------
# _post_async — delegation to RpiTelemetryCollector / RpiTelemetrySender
# ---------------------------------------------------------------------------

class TestPostAsync:
    """`_post_async` now delegates sending to the shared PEN-166 module
    (`edge/vision/telemetry`) instead of an inline `urllib` call. These tests
    assert VideoTelemetry wires its constructor args through to the sender
    correctly and handles buffering/error paths -- the HTTP-level details
    (batching, retries, 207 handling) are covered by
    `edge/vision/telemetry/tests/test_sender.py`.
    """

    def _make_enabled(self, endpoint="https://example.com/unifiedIngress", api_key="secret", **kwargs):
        return VideoTelemetry(
            endpoint_url=endpoint,
            api_key=api_key,
            telemetry_enabled=True,
            **kwargs,
        )

    def _make_event(self, event_type="video_stream_stop"):
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "source": "rpi",
            "timestamp": _utc_now_iso(),
            "device_id": "rpi-01",
            "session_id": "sess-1",
            "version": "1.0",
            "payload": {"reason": "test"},
        }

    def test_sender_constructed_with_endpoint_as_url(self):
        tel = self._make_enabled(endpoint="https://example.com/unifiedIngress")
        with patch("video_telemetry.RpiTelemetrySender") as mock_sender_cls:
            mock_sender_cls.return_value.flush_and_send.return_value = True
            tel._post_async(self._make_event())

        _, kwargs = mock_sender_cls.call_args
        assert kwargs["endpoint"] == "https://example.com/unifiedIngress"

    def test_sender_constructed_with_api_key_as_device_token(self):
        tel = self._make_enabled(api_key="my-device-token")
        with patch("video_telemetry.RpiTelemetrySender") as mock_sender_cls:
            mock_sender_cls.return_value.flush_and_send.return_value = True
            tel._post_async(self._make_event())

        _, kwargs = mock_sender_cls.call_args
        assert kwargs["device_token"] == "my-device-token"

    def test_sender_constructed_with_device_id(self):
        tel = self._make_enabled(device_id="rpi-test-01")
        with patch("video_telemetry.RpiTelemetrySender") as mock_sender_cls:
            mock_sender_cls.return_value.flush_and_send.return_value = True
            tel._post_async(self._make_event())

        _, kwargs = mock_sender_cls.call_args
        assert kwargs["device_id"] == "rpi-test-01"

    def test_sender_constructed_once_and_reused(self):
        tel = self._make_enabled()
        with patch("video_telemetry.RpiTelemetrySender") as mock_sender_cls:
            mock_sender_cls.return_value.flush_and_send.return_value = True
            tel._post_async(self._make_event())
            tel._post_async(self._make_event())

        mock_sender_cls.assert_called_once()

    def test_event_is_buffered_before_send(self):
        tel = self._make_enabled()
        event = self._make_event()
        with patch("video_telemetry.RpiTelemetrySender") as mock_sender_cls:
            mock_sender_cls.return_value.flush_and_send.return_value = True
            tel._post_async(event)

        mock_sender_cls.return_value.flush_and_send.assert_called_once()
        collector_arg = mock_sender_cls.return_value.flush_and_send.call_args[0][0]
        assert event in collector_arg.peek()

    def test_empty_endpoint_skips_send(self):
        tel = VideoTelemetry(endpoint_url="", api_key="k", telemetry_enabled=True)
        with patch("video_telemetry.RpiTelemetrySender") as mock_sender_cls:
            tel._post_async(self._make_event())

        mock_sender_cls.assert_not_called()

    def test_send_error_is_swallowed(self):
        tel = self._make_enabled()
        with patch("video_telemetry.RpiTelemetrySender") as mock_sender_cls:
            mock_sender_cls.return_value.flush_and_send.side_effect = OSError("boom")
            # Should not raise
            tel._post_async(self._make_event())

    def test_sender_construction_error_is_swallowed(self):
        tel = self._make_enabled()
        with patch("video_telemetry.RpiTelemetrySender", side_effect=ValueError("bad endpoint")):
            # Should not raise
            tel._post_async(self._make_event())

    def test_emit_runs_in_background_thread(self):
        tel = self._make_enabled()
        thread_names = []

        original_start = threading.Thread.start

        def capture_start(self_thread):
            thread_names.append(self_thread.name)
            original_start(self_thread)

        # Prevent actual sends
        with patch.object(tel, "_post_async"):
            with patch.object(threading.Thread, "start", capture_start):
                tel.emit_stream_stop("test")
                # Allow thread to start
                time.sleep(0.05)

        assert any("telemetry-" in n for n in thread_names)


# ---------------------------------------------------------------------------
# emit_stream_stop — blocking / non-daemon behaviour
# ---------------------------------------------------------------------------

class TestEmitStreamStopBlocking:
    """emit_stream_stop must use a non-daemon thread and join it so that the
    stop event is not lost when the Python process exits immediately after
    UDPVideoStreamer.stop() returns."""

    def _make_enabled(self):
        return VideoTelemetry(
            endpoint_url="https://example.com/tel",
            api_key="k",
            telemetry_enabled=True,
        )

    def test_emit_stream_stop_spawns_non_daemon_thread(self):
        tel = self._make_enabled()
        spawned: list[threading.Thread] = []

        original_init = threading.Thread.__init__

        def capture_init(self_thread, *args, **kwargs):
            original_init(self_thread, *args, **kwargs)
            spawned.append(self_thread)

        with patch.object(tel, "_post_async"):
            with patch.object(threading.Thread, "__init__", capture_init):
                tel.emit_stream_stop("keyboard_interrupt")

        stop_threads = [t for t in spawned if "video_stream_stop" in t.name]
        assert stop_threads, "No thread named 'telemetry-video_stream_stop' was created"
        assert not stop_threads[0].daemon, "emit_stream_stop thread must be non-daemon"

    def test_emit_stream_start_still_uses_daemon_thread(self):
        tel = self._make_enabled()
        spawned: list[threading.Thread] = []

        original_init = threading.Thread.__init__

        def capture_init(self_thread, *args, **kwargs):
            original_init(self_thread, *args, **kwargs)
            spawned.append(self_thread)

        with patch.object(tel, "_post_async"):
            with patch.object(threading.Thread, "__init__", capture_init):
                tel.emit_stream_start("udp", 9999, 1280, 720, 30.0)

        start_threads = [t for t in spawned if "video_stream_start" in t.name]
        assert start_threads, "No thread named 'telemetry-video_stream_start' was created"
        assert start_threads[0].daemon, "emit_stream_start thread must be daemon (fire-and-forget)"

    def test_emit_stream_health_still_uses_daemon_thread(self):
        tel = self._make_enabled()
        spawned: list[threading.Thread] = []

        original_init = threading.Thread.__init__

        def capture_init(self_thread, *args, **kwargs):
            original_init(self_thread, *args, **kwargs)
            spawned.append(self_thread)

        with patch.object(tel, "_post_async"):
            with patch.object(threading.Thread, "__init__", capture_init):
                tel.emit_stream_health(29.5, 2, 3, 120.0)

        health_threads = [t for t in spawned if "video_stream_health" in t.name]
        assert health_threads, "No thread named 'telemetry-video_stream_health' was created"
        assert health_threads[0].daemon, "emit_stream_health thread must be daemon (fire-and-forget)"

    def test_emit_stream_stop_joins_thread_within_timeout(self):
        """emit_stream_stop must block until the send thread completes (or times out)."""
        tel = self._make_enabled()
        join_called = []

        original_join = threading.Thread.join

        def capture_join(self_thread, timeout=None):
            join_called.append(timeout)
            return original_join(self_thread, timeout=timeout)

        with patch.object(tel, "_post_async"):
            with patch.object(threading.Thread, "join", capture_join):
                tel.emit_stream_stop("stop_called")

        assert join_called, "Thread.join was never called — stop event may be lost at shutdown"
        assert join_called[0] == tel.timeout_seconds, (
            f"join timeout {join_called[0]!r} != timeout_seconds {tel.timeout_seconds!r}"
        )

    def test_emit_stream_stop_disabled_is_noop(self):
        tel = VideoTelemetry(telemetry_enabled=False)
        with patch.object(tel, "_post_async") as mock_post:
            tel.emit_stream_stop("keyboard_interrupt")
            mock_post.assert_not_called()
