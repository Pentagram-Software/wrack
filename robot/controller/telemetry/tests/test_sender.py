"""Unit tests for telemetry.sender.TelemetrySender."""

import json
import threading
import time
from unittest.mock import MagicMock, patch, call

import pytest

from telemetry.sender import TelemetrySender, SendError
from telemetry.collector import TelemetryCollector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENDPOINT = "https://example.cloudfunctions.net/telemetryIngestion"
API_KEY = "test-api-key"


def _make_events(n: int = 3) -> list:
    return [
        {
            "event_id": f"id-{i}",
            "event_type": "battery_status",
            "source": "ev3",
            "timestamp": "2026-01-01T00:00:00Z",
            "session_id": "sess-1",
            "payload": {"voltage_mv": 7200, "percentage": 85},
        }
        for i in range(n)
    ]


def _mock_response(status_code: int = 200, text: str = "OK"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Basic construction
# ---------------------------------------------------------------------------


class TestInit:
    def test_defaults(self):
        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY)
        assert s.endpoint == ENDPOINT
        assert s.api_key == API_KEY
        assert s.max_batch_size == 100
        assert s.max_retries == 3
        assert s.retry_base_delay == 2.0
        assert s.timeout == 10.0

    def test_custom_params(self):
        s = TelemetrySender(
            endpoint=ENDPOINT,
            api_key=API_KEY,
            max_batch_size=50,
            max_retries=1,
            retry_base_delay=0.1,
            timeout=5.0,
        )
        assert s.max_batch_size == 50
        assert s.max_retries == 1


# ---------------------------------------------------------------------------
# send() — happy path
# ---------------------------------------------------------------------------


class TestSend:
    @patch("telemetry.sender._requests")
    def test_send_posts_to_endpoint(self, mock_requests):
        mock_requests.post.return_value = _mock_response()
        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY)
        s.send(_make_events(2))
        mock_requests.post.assert_called_once()
        url = mock_requests.post.call_args[0][0]
        assert url == ENDPOINT

    @patch("telemetry.sender._requests")
    def test_send_includes_api_key_header(self, mock_requests):
        mock_requests.post.return_value = _mock_response()
        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY)
        s.send(_make_events(1))
        headers = mock_requests.post.call_args[1]["headers"]
        assert headers["X-API-Key"] == API_KEY

    @patch("telemetry.sender._requests")
    def test_send_sets_json_content_type(self, mock_requests):
        mock_requests.post.return_value = _mock_response()
        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY)
        s.send(_make_events(1))
        headers = mock_requests.post.call_args[1]["headers"]
        assert headers["Content-Type"] == "application/json"

    @patch("telemetry.sender._requests")
    def test_send_body_contains_events(self, mock_requests):
        mock_requests.post.return_value = _mock_response()
        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY)
        events = _make_events(2)
        s.send(events)
        body = json.loads(mock_requests.post.call_args[1]["data"])
        assert "events" in body
        assert len(body["events"]) == 2

    @patch("telemetry.sender._requests")
    def test_send_empty_list_is_noop(self, mock_requests):
        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY)
        s.send([])
        mock_requests.post.assert_not_called()

    @patch("telemetry.sender._requests")
    def test_send_passes_timeout(self, mock_requests):
        mock_requests.post.return_value = _mock_response()
        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY, timeout=7.0)
        s.send(_make_events(1))
        timeout = mock_requests.post.call_args[1]["timeout"]
        assert timeout == 7.0


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


class TestBatching:
    @patch("telemetry.sender._requests")
    def test_large_list_split_into_batches(self, mock_requests):
        mock_requests.post.return_value = _mock_response()
        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY, max_batch_size=10)
        s.send(_make_events(25))
        # 25 events / 10 per batch = 3 POST calls
        assert mock_requests.post.call_count == 3

    @patch("telemetry.sender._requests")
    def test_exact_batch_boundary(self, mock_requests):
        mock_requests.post.return_value = _mock_response()
        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY, max_batch_size=5)
        s.send(_make_events(5))
        assert mock_requests.post.call_count == 1

    @patch("telemetry.sender._requests")
    def test_batch_sizes_in_bodies(self, mock_requests):
        mock_requests.post.return_value = _mock_response()
        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY, max_batch_size=4)
        s.send(_make_events(9))
        calls = mock_requests.post.call_args_list
        sizes = [len(json.loads(c[1]["data"])["events"]) for c in calls]
        assert sizes == [4, 4, 1]


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetry:
    @patch("telemetry.sender.time")
    @patch("telemetry.sender._requests")
    def test_retries_on_network_error(self, mock_requests, mock_time):
        mock_requests.post.side_effect = [
            ConnectionError("timeout"),
            ConnectionError("timeout"),
            _mock_response(200),
        ]
        mock_time.sleep = MagicMock()
        s = TelemetrySender(
            endpoint=ENDPOINT,
            api_key=API_KEY,
            max_retries=3,
            retry_base_delay=0.1,
        )
        s.send(_make_events(1))
        assert mock_requests.post.call_count == 3

    @patch("telemetry.sender.time")
    @patch("telemetry.sender._requests")
    def test_raises_send_error_after_all_retries(self, mock_requests, mock_time):
        mock_requests.post.side_effect = ConnectionError("timeout")
        mock_time.sleep = MagicMock()
        s = TelemetrySender(
            endpoint=ENDPOINT,
            api_key=API_KEY,
            max_retries=2,
            retry_base_delay=0.1,
        )
        with pytest.raises(SendError):
            s.send(_make_events(1))
        assert mock_requests.post.call_count == 2

    @patch("telemetry.sender.time")
    @patch("telemetry.sender._requests")
    def test_exponential_backoff_delays(self, mock_requests, mock_time):
        mock_requests.post.side_effect = [
            ConnectionError(),
            ConnectionError(),
            _mock_response(200),
        ]
        sleep_calls = []
        mock_time.sleep.side_effect = lambda d: sleep_calls.append(d)
        s = TelemetrySender(
            endpoint=ENDPOINT,
            api_key=API_KEY,
            max_retries=3,
            retry_base_delay=1.0,
        )
        s.send(_make_events(1))
        # First retry: 1.0 s, second retry: 2.0 s
        assert sleep_calls == [1.0, 2.0]

    @patch("telemetry.sender.time")
    @patch("telemetry.sender._requests")
    def test_http_error_triggers_retry(self, mock_requests, mock_time):
        mock_requests.post.side_effect = [
            _mock_response(500, "Internal Server Error"),
            _mock_response(200),
        ]
        mock_time.sleep = MagicMock()
        s = TelemetrySender(
            endpoint=ENDPOINT,
            api_key=API_KEY,
            max_retries=2,
            retry_base_delay=0.1,
        )
        s.send(_make_events(1))
        assert mock_requests.post.call_count == 2


# ---------------------------------------------------------------------------
# send_from_collector()
# ---------------------------------------------------------------------------


class TestSendFromCollector:
    @patch("telemetry.sender._requests")
    def test_flushes_collector_and_sends(self, mock_requests):
        mock_requests.post.return_value = _mock_response()
        c = TelemetryCollector()
        c.collect("battery_status", voltage_mv=7200, percentage=85)
        c.collect("motor_status", motors={})

        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY)
        thread = s.send_from_collector(c)
        if thread is not None:
            thread.join(timeout=5)

        assert c.size() == 0
        mock_requests.post.assert_called_once()

    @patch("telemetry.sender._requests")
    def test_empty_collector_does_not_post(self, mock_requests):
        c = TelemetryCollector()
        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY)
        result = s.send_from_collector(c)
        assert result is None
        mock_requests.post.assert_not_called()

    @patch("telemetry.sender._requests")
    def test_background_send_uses_daemon_thread(self, mock_requests):
        mock_requests.post.return_value = _mock_response()
        c = TelemetryCollector()
        c.collect("battery_status", voltage_mv=7200, percentage=85)

        s = TelemetrySender(endpoint=ENDPOINT, api_key=API_KEY)
        thread = s.send_from_collector(c)
        if thread is not None:
            assert thread.daemon
            thread.join(timeout=5)
