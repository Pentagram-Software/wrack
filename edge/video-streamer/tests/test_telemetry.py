"""
Unit tests for edge/video-streamer/telemetry.py.

All HTTP calls are mocked so no real network requests are made.
"""

import json
import threading
import time
import unittest.mock as mock
from unittest.mock import MagicMock, patch, call
from urllib.error import URLError

import pytest

from telemetry import VideoTelemetry, _utc_now_iso


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
# HTTP POST — _post_async
# ---------------------------------------------------------------------------

class TestPostAsync:
    def _make_enabled(self, endpoint="https://example.com/tel", api_key="secret"):
        return VideoTelemetry(
            endpoint_url=endpoint,
            api_key=api_key,
            telemetry_enabled=True,
        )

    def test_post_sends_json_body(self):
        tel = self._make_enabled()
        event = {
            "event_id": "abc",
            "event_type": "video_stream_stop",
            "source": "rpi",
            "timestamp": "2026-01-01T00:00:00.000Z",
            "payload": {"reason": "test"},
            "device_id": "rpi-01",
            "session_id": "sess-1",
            "version": "1.0",
        }

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("telemetry.urllib_request.urlopen", return_value=mock_response) as mock_open:
            tel._post_async(event)

        mock_open.assert_called_once()
        req = mock_open.call_args[0][0]
        body = json.loads(req.data.decode())
        assert "events" in body
        assert len(body["events"]) == 1
        assert body["events"][0]["event_type"] == "video_stream_stop"

    def test_post_sets_content_type_header(self):
        tel = self._make_enabled()
        event = {"event_id": "x", "event_type": "test", "payload": {}}

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("telemetry.urllib_request.urlopen", return_value=mock_response) as mock_open:
            tel._post_async(event)

        req = mock_open.call_args[0][0]
        assert req.get_header("Content-type") == "application/json"

    def test_post_sets_api_key_header(self):
        tel = self._make_enabled(api_key="my-api-key")
        event = {"event_id": "x", "event_type": "test", "payload": {}}

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("telemetry.urllib_request.urlopen", return_value=mock_response) as mock_open:
            tel._post_async(event)

        req = mock_open.call_args[0][0]
        assert req.get_header("X-api-key") == "my-api-key"

    def test_url_error_is_swallowed(self):
        tel = self._make_enabled()
        event = {"event_id": "x", "event_type": "test", "payload": {}}

        with patch("telemetry.urllib_request.urlopen", side_effect=URLError("connection refused")):
            # Should not raise
            tel._post_async(event)

    def test_empty_endpoint_skips_post(self):
        tel = VideoTelemetry(endpoint_url="", api_key="k", telemetry_enabled=True)
        event = {"event_id": "x", "event_type": "test", "payload": {}}

        with patch("telemetry.urllib_request.urlopen") as mock_open:
            tel._post_async(event)
            mock_open.assert_not_called()

    def test_emit_runs_in_background_thread(self):
        tel = VideoTelemetry(
            endpoint_url="https://example.com/tel",
            api_key="k",
            telemetry_enabled=True,
        )
        thread_names = []

        original_start = threading.Thread.start

        def capture_start(self_thread):
            thread_names.append(self_thread.name)
            original_start(self_thread)

        # Prevent actual HTTP calls
        with patch.object(tel, "_post_async"):
            with patch.object(threading.Thread, "start", capture_start):
                tel.emit_stream_stop("test")
                # Allow thread to start
                time.sleep(0.05)

        assert any("telemetry-" in n for n in thread_names)
