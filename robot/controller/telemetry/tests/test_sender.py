"""Unit tests for telemetry/sender.py."""

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from telemetry.sender import (
    TelemetrySender,
    PartialFailureError,
    NonRetryablePartialFailureError,
    DEFAULT_BATCH_SIZE,
)
from telemetry.collector import TelemetryCollector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uid() -> str:
    return str(uuid.uuid4())


def _make_event(event_type: str = "battery_status") -> dict:
    return {
        "event_id": _uid(),
        "event_type": event_type,
        "source": "ev3",
        "timestamp": _ts(),
        "payload": {"voltage_mv": 7200, "percentage": 85.0},
    }


def _make_sender(**kwargs) -> TelemetrySender:
    defaults = {
        "endpoint": "https://example.com/telemetryIngestion",
        "api_key": "test-api-key",
        "max_retries": 0,
        "timeout": 5,
    }
    defaults.update(kwargs)
    return TelemetrySender(**defaults)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestTelemetrySenderInit:
    def test_stores_endpoint(self):
        s = _make_sender(endpoint="https://my.endpoint/fn")
        assert s.endpoint == "https://my.endpoint/fn"

    def test_stores_api_key(self):
        s = _make_sender(api_key="secret")
        assert s.api_key == "secret"

    def test_default_batch_size(self):
        s = _make_sender()
        assert s.batch_size == DEFAULT_BATCH_SIZE

    def test_custom_batch_size(self):
        s = _make_sender(batch_size=10)
        assert s.batch_size == 10

    def test_default_max_retries(self):
        s = TelemetrySender(
            endpoint="https://example.com/fn",
            api_key="k",
        )
        assert s.max_retries == 3  # DEFAULT_MAX_RETRIES

    def test_callbacks_default_to_none(self):
        s = _make_sender()
        assert s.on_success is None
        assert s.on_error is None


# ---------------------------------------------------------------------------
# send_events — empty list
# ---------------------------------------------------------------------------

class TestSendEventsEmpty:
    def test_returns_true_for_empty_list(self):
        s = _make_sender()
        assert s.send_events([]) is True

    def test_no_http_call_for_empty_list(self):
        s = _make_sender()
        with patch("telemetry.sender._http") as mock_http:
            result = s.send_events([])
        mock_http.post.assert_not_called()
        assert result is True


# ---------------------------------------------------------------------------
# send_events — successful POST
# ---------------------------------------------------------------------------

class TestSendEventsSuccess:
    def _mock_response(self, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        return resp

    def test_posts_to_correct_endpoint(self):
        s = _make_sender(endpoint="https://test.example/fn")
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            s.send_events(events)
        args, kwargs = mock_http.post.call_args
        assert args[0] == "https://test.example/fn"

    def test_includes_api_key_header(self):
        s = _make_sender(api_key="my-key")
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            s.send_events(events)
        _, kwargs = mock_http.post.call_args
        headers = kwargs.get("headers", {})
        assert headers.get("X-API-Key") == "my-key"

    def test_sends_json_content_type(self):
        s = _make_sender()
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            s.send_events(events)
        _, kwargs = mock_http.post.call_args
        headers = kwargs.get("headers", {})
        assert headers.get("Content-Type") == "application/json"

    def test_body_contains_events_key(self):
        s = _make_sender()
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            s.send_events(events)
        _, kwargs = mock_http.post.call_args
        body = json.loads(kwargs["data"])
        assert "events" in body
        assert len(body["events"]) == 1

    def test_returns_true_on_success(self):
        s = _make_sender()
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            result = s.send_events(events)
        assert result is True

    def test_on_success_callback_called(self):
        callback = MagicMock()
        s = _make_sender(on_success=callback)
        events = [_make_event(), _make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            s.send_events(events)
        callback.assert_called_once_with(2)


# ---------------------------------------------------------------------------
# send_events — batching
# ---------------------------------------------------------------------------

class TestSendEventsBatching:
    def _mock_response(self, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        return resp

    def test_single_batch_for_small_list(self):
        s = _make_sender(batch_size=100)
        events = [_make_event() for _ in range(5)]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            s.send_events(events)
        assert mock_http.post.call_count == 1

    def test_multiple_batches_for_large_list(self):
        s = _make_sender(batch_size=3)
        events = [_make_event() for _ in range(7)]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            s.send_events(events)
        # ceil(7/3) = 3 batches
        assert mock_http.post.call_count == 3

    def test_batch_sizes_correct(self):
        s = _make_sender(batch_size=3)
        events = [_make_event() for _ in range(7)]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            s.send_events(events)
        batch_sizes = []
        for c in mock_http.post.call_args_list:
            body = json.loads(c[1]["data"])
            batch_sizes.append(len(body["events"]))
        assert sorted(batch_sizes) == [1, 3, 3]

    def test_all_events_sent_across_batches(self):
        s = _make_sender(batch_size=2)
        ids = [_uid() for _ in range(5)]
        events = []
        for eid in ids:
            e = _make_event()
            e["event_id"] = eid
            events.append(e)
        sent_ids = []
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            s.send_events(events)
        for c in mock_http.post.call_args_list:
            body = json.loads(c[1]["data"])
            sent_ids.extend(ev["event_id"] for ev in body["events"])
        assert sorted(sent_ids) == sorted(ids)


# ---------------------------------------------------------------------------
# send_events — HTTP errors and retries
# ---------------------------------------------------------------------------

class TestSendEventsFailure:
    def _error_response(self, status_code=500):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = "Internal Server Error"
        return resp

    def test_returns_false_on_http_500(self):
        s = _make_sender(max_retries=0)
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._error_response(500)
            result = s.send_events(events)
        assert result is False

    def test_returns_false_on_network_exception(self):
        s = _make_sender(max_retries=0)
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.side_effect = ConnectionError("network down")
            result = s.send_events(events)
        assert result is False

    def test_retries_on_transient_failure(self):
        s = _make_sender(max_retries=2)
        events = [_make_event()]
        ok_response = MagicMock()
        ok_response.status_code = 200

        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._time") as mock_time:
            mock_http.post.side_effect = [
                ConnectionError("fail 1"),
                ConnectionError("fail 2"),
                ok_response,
            ]
            result = s.send_events(events)
        assert result is True
        assert mock_http.post.call_count == 3

    def test_on_error_callback_called_after_all_retries(self):
        error_cb = MagicMock()
        s = _make_sender(max_retries=1, on_error=error_cb)
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._time"):
            mock_http.post.side_effect = ConnectionError("down")
            s.send_events(events)
        error_cb.assert_called_once()
        assert isinstance(error_cb.call_args[0][0], ConnectionError)

    def test_partial_failure_returns_false(self):
        """If one batch fails and another succeeds, overall result is False."""
        s = _make_sender(max_retries=0, batch_size=1)
        events = [_make_event(), _make_event()]
        ok_response = MagicMock()
        ok_response.status_code = 200
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.side_effect = [
                ok_response,
                self._error_response(503),
            ]
            result = s.send_events(events)
        assert result is False


# ---------------------------------------------------------------------------
# send_events_async
# ---------------------------------------------------------------------------

class TestSendEventsAsync:
    def test_returns_immediately(self):
        s = _make_sender()
        events = [_make_event()]
        started = threading.Event()
        done = threading.Event()

        def slow_post(*args, **kwargs):
            started.set()
            done.wait(timeout=2)
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.side_effect = slow_post
            s.send_events_async(events)
            started.wait(timeout=1)
        done.set()

    def test_empty_list_does_not_spawn_thread(self):
        s = _make_sender()
        with patch("threading.Thread") as mock_thread:
            s.send_events_async([])
        mock_thread.assert_not_called()

    def test_success_callback_called_in_background(self):
        results = []
        s = _make_sender(on_success=lambda n: results.append(n))
        events = [_make_event()]
        ok_response = MagicMock()
        ok_response.status_code = 200
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = ok_response
            s.send_events_async(events)
            # Wait for background thread to finish
            time.sleep(0.1)
        assert results == [1]


# ---------------------------------------------------------------------------
# flush_and_send
# ---------------------------------------------------------------------------

class TestFlushAndSend:
    def test_flushes_collector_and_sends(self):
        s = _make_sender()
        c = TelemetryCollector()
        c.collect_battery_status(7000, 80.0)
        c.collect_command_received("stop")

        ok_response = MagicMock()
        ok_response.status_code = 200

        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = ok_response
            result = s.flush_and_send(c)

        assert result is True
        assert c.buffer_size == 0  # collector was flushed

    def test_returns_true_for_empty_collector(self):
        s = _make_sender()
        c = TelemetryCollector()
        result = s.flush_and_send(c)
        assert result is True

    def test_async_returns_none(self):
        s = _make_sender()
        c = TelemetryCollector()
        c.collect_battery_status(7000, 80.0)
        ok_response = MagicMock()
        ok_response.status_code = 200
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = ok_response
            result = s.flush_and_send(c, async_send=True)
        assert result is None

    def test_restores_collector_events_after_send_failure(self):
        """Failed sync send should restore flushed events back to collector."""
        s = _make_sender(max_retries=0)
        c = TelemetryCollector()
        c.collect_battery_status(7000, 80.0)
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.side_effect = ConnectionError("down")
            s.flush_and_send(c)
        assert c.buffer_size == 1

    def test_restores_only_unsent_suffix_after_partial_send(self):
        """If first batch succeeds and second fails, restore only unsent events."""
        s = _make_sender(max_retries=0, batch_size=1)
        c = TelemetryCollector()
        c.collect_battery_status(7000, 80.0)
        c.collect_command_received("stop")

        ok_response = MagicMock()
        ok_response.status_code = 200
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.side_effect = [ok_response, ConnectionError("down")]
            result = s.flush_and_send(c)

        assert result is False
        assert c.buffer_size == 1

    def test_async_flush_restores_unsent_events_on_failure(self):
        """Async flush should also re-buffer events when send ultimately fails."""
        s = _make_sender(max_retries=0)
        c = TelemetryCollector()
        c.collect_battery_status(7000, 80.0)

        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.side_effect = ConnectionError("down")
            result = s.flush_and_send(c, async_send=True)
            assert result is None
            time.sleep(0.1)

        assert c.buffer_size == 1


# ---------------------------------------------------------------------------
# HTTP 207 Multi-Status — partial batch failure
# ---------------------------------------------------------------------------

class TestSendEvents207Partial:
    """HTTP 207 from the Cloud Function signals a partial failure that IS retried.

    The Cloud Function (telemetry.js) returns 207 with ``success: false``
    when at least one event fails schema validation or BigQuery insert.
    ``telemetry.js`` passes each row's ``event_id`` as the BigQuery
    ``insertId``, so retrying the full batch is safe — already-accepted rows
    are deduplicated by BigQuery's streaming buffer (~1-minute window).

    Correct behaviour: raise ``PartialFailureError`` and retry with
    exponential back-off, just like any other transient failure.  After all
    retries are exhausted, surface the error via ``on_error`` and return
    ``False``.
    """

    def _207_response(self, inserted: int = 1, failed: int = 1):
        resp = MagicMock()
        resp.status_code = 207
        resp.text = json.dumps({
            "success": False,
            "inserted": inserted,
            "failed": failed,
            "errors": [
                {"index": 1, "event_id": "bad-id", "errors": ["event_type is required"]}
            ],
        })
        return resp

    def _207_bigquery_partial_response(self):
        resp = MagicMock()
        resp.status_code = 207
        resp.text = json.dumps({
            "success": False,
            "inserted": 1,
            "failed": 1,
            "errors": [
                {"event_id": "evt-bq", "errors": ["backendError"]}
            ],
        })
        return resp

    def test_returns_false_on_207(self):
        s = _make_sender(max_retries=0)
        events = [_make_event(), _make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._207_response()
            result = s.send_events(events)
        assert result is False

    def test_on_error_callback_called_on_207(self):
        error_cb = MagicMock()
        s = _make_sender(max_retries=0, on_error=error_cb)
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._207_response()
            s.send_events(events)
        error_cb.assert_called_once()
        exc = error_cb.call_args[0][0]
        assert isinstance(exc, PartialFailureError)
        assert isinstance(exc, IOError)  # PartialFailureError is a subclass of IOError
        assert "207" in str(exc)

    def test_207_is_retried_up_to_max_retries(self):
        """207 must be retried — insertId makes full-batch retries safe."""
        s = _make_sender(max_retries=2)
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._time"):
            mock_http.post.return_value = self._207_bigquery_partial_response()
            result = s.send_events(events)
        assert result is False
        assert mock_http.post.call_count == 3  # initial attempt + 2 retries

    def test_207_is_not_treated_as_success(self):
        """Ensure on_success callback is NOT called for a 207 response."""
        success_cb = MagicMock()
        s = _make_sender(max_retries=0, on_success=success_cb)
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._207_response()
            s.send_events(events)
        success_cb.assert_not_called()

    def test_207_error_message_contains_response_body(self):
        """Error surfaced to on_error should include partial-failure details."""
        errors_received = []
        s = _make_sender(max_retries=0, on_error=lambda e: errors_received.append(e))
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._207_response(inserted=3, failed=2)
            s.send_events(events)
        assert errors_received
        assert "207" in str(errors_received[0])

    def test_partial_failure_error_is_subclass_of_ioerror(self):
        """PartialFailureError must be an IOError for API compatibility."""
        assert issubclass(PartialFailureError, IOError)

    def test_207_recovers_on_subsequent_success(self):
        """If a retry after 207 returns 200, the batch is reported as sent."""
        s = _make_sender(max_retries=2)
        events = [_make_event()]
        ok_response = MagicMock()
        ok_response.status_code = 200
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._time"):
            mock_http.post.side_effect = [self._207_bigquery_partial_response(), ok_response]
            result = s.send_events(events)
        assert result is True
        assert mock_http.post.call_count == 2

    def test_207_validation_failure_is_not_retried(self):
        """Validation-only 207 should fail fast without retry loop."""
        s = _make_sender(max_retries=3, on_error=MagicMock())
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._time"):
            mock_http.post.return_value = self._207_response()
            result = s.send_events(events)
        assert result is False
        assert mock_http.post.call_count == 1
        err = s.on_error.call_args[0][0]
        assert isinstance(err, NonRetryablePartialFailureError)


# ---------------------------------------------------------------------------
# No HTTP library available
# ---------------------------------------------------------------------------

class TestNoHttpLibrary:
    def test_returns_false_when_no_http_lib(self):
        s = _make_sender()
        events = [_make_event()]
        with patch("telemetry.sender._http", None):
            result = s.send_events(events)
        assert result is False
