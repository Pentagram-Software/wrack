"""Unit tests for telemetry/sender.py."""

import json
import os
import tempfile
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

    def test_rejects_zero_batch_size(self):
        with pytest.raises(ValueError):
            _make_sender(batch_size=0)

    def test_rejects_negative_batch_size(self):
        with pytest.raises(ValueError):
            _make_sender(batch_size=-5)

    def test_rejects_negative_max_retries(self):
        with pytest.raises(ValueError):
            _make_sender(max_retries=-1)


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

    def test_falls_back_to_sync_send_without_threading(self):
        """Without threading (some MicroPython builds) async sends run inline."""
        results = []
        s = _make_sender(on_success=lambda n: results.append(n))
        ok_response = MagicMock()
        ok_response.status_code = 200
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._HAS_THREADING", False), \
             patch("telemetry.sender._threading", None):
            mock_http.post.return_value = ok_response
            s.send_events_async([_make_event()])
            # Ran synchronously — no thread to wait for.
            assert results == [1]

    def test_sync_fallback_rebuffers_on_failure(self):
        """Sync async-fallback still restores unsent events to the collector."""
        s = _make_sender(max_retries=0)
        c = TelemetryCollector()
        c.collect_battery_status(7000, 80.0)
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._HAS_THREADING", False), \
             patch("telemetry.sender._threading", None):
            mock_http.post.side_effect = ConnectionError("down")
            result = s.flush_and_send(c, async_send=True)
        assert result is None
        assert c.buffer_size == 1


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

    def test_flush_and_send_drains_overflow_file(self):
        """Persisted overflow events are sent alongside the in-memory buffer."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            os.remove(path)
            c = TelemetryCollector(max_buffer_size=2, overflow_path=path)
            for i in range(4):  # 2 stay buffered, 2 spill to overflow file
                c.collect_battery_status(7000 + i, float(i))
            assert len(c.load_overflow()) == 2

            sent_ids = []
            ok_response = MagicMock()
            ok_response.status_code = 200
            s = _make_sender(batch_size=100)
            with patch("telemetry.sender._http") as mock_http:
                mock_http.post.return_value = ok_response
                result = s.flush_and_send(c)
                for cargs in mock_http.post.call_args_list:
                    body = json.loads(cargs[1]["data"])
                    sent_ids.extend(ev["event_id"] for ev in body["events"])

            assert result is True
            assert len(sent_ids) == 4  # overflow (2) + buffer (2)
            assert c.buffer_size == 0
            assert c.load_overflow() == []  # overflow file drained
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_flush_and_send_failure_preserves_overflow_events(self):
        """A failed drain re-buffers/re-persists events instead of losing them."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            os.remove(path)
            c = TelemetryCollector(max_buffer_size=2, overflow_path=path)
            for i in range(4):
                c.collect_battery_status(7000 + i, float(i))
            assert len(c.load_overflow()) == 2

            s = _make_sender(max_retries=0)
            with patch("telemetry.sender._http") as mock_http:
                mock_http.post.side_effect = ConnectionError("down")
                result = s.flush_and_send(c)

            assert result is False
            # All four events preserved across buffer + overflow, none lost.
            assert c.buffer_size + len(c.load_overflow()) == 4
        finally:
            if os.path.exists(path):
                os.remove(path)

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
    """HTTP 207 from the Cloud Function signals a partial batch failure.

    The Cloud Function (telemetry.js) returns 207 with ``success: false`` when
    at least one event fails.  The response body is parsed per-event:

    * Validation failures carry an ``index`` (batch position) and are
      *permanent* — re-sending the same payload would fail identically, so the
      event is dropped and never re-buffered.
    * BigQuery streaming failures carry an ``event_id`` and are *retryable* —
      only the failing subset is re-sent.  ``telemetry.js`` passes each row's
      ``event_id`` as the BigQuery ``insertId``, so already-accepted rows are
      de-duplicated by the streaming buffer (~1-minute window).
    """

    def _validation_207(self, indices, inserted=0, failed=None):
        """A 207 where the given batch *indices* failed schema validation."""
        resp = MagicMock()
        resp.status_code = 207
        resp.text = json.dumps({
            "success": False,
            "inserted": inserted,
            "failed": failed if failed is not None else len(indices),
            "errors": [
                {"index": i, "event_id": None, "errors": ["event_type is required"]}
                for i in indices
            ],
        })
        return resp

    def _bigquery_207(self, event_ids, inserted=0, failed=None):
        """A 207 where the given *event_ids* hit transient BigQuery errors."""
        resp = MagicMock()
        resp.status_code = 207
        resp.text = json.dumps({
            "success": False,
            "inserted": inserted,
            "failed": failed if failed is not None else len(event_ids),
            "errors": [
                {"event_id": eid, "errors": ["backendError"]} for eid in event_ids
            ],
        })
        return resp

    def test_returns_false_on_207(self):
        s = _make_sender(max_retries=0)
        events = [_make_event(), _make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._validation_207([1], inserted=1)
            result = s.send_events(events)
        assert result is False

    def test_on_error_callback_called_on_retryable_207(self):
        error_cb = MagicMock()
        s = _make_sender(max_retries=0, on_error=error_cb)
        event = _make_event()
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._bigquery_207([event["event_id"]])
            s.send_events([event])
        error_cb.assert_called_once()
        exc = error_cb.call_args[0][0]
        assert isinstance(exc, PartialFailureError)
        assert isinstance(exc, IOError)  # PartialFailureError is a subclass of IOError
        assert "207" in str(exc)

    def test_retryable_207_is_retried_up_to_max_retries(self):
        """A transient (BigQuery) 207 is retried with the failing subset."""
        s = _make_sender(max_retries=2)
        event = _make_event()
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._time"):
            mock_http.post.return_value = self._bigquery_207([event["event_id"]])
            result = s.send_events([event])
        assert result is False
        assert mock_http.post.call_count == 3  # initial attempt + 2 retries

    def test_207_does_not_call_success_for_failed_events(self):
        """on_success must not count permanently-rejected events."""
        success_cb = MagicMock()
        s = _make_sender(max_retries=0, on_success=success_cb)
        event = _make_event()
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._validation_207([0])
            s.send_events([event])
        success_cb.assert_not_called()

    def test_validation_failure_error_is_informative(self):
        errors_received = []
        s = _make_sender(max_retries=0, on_error=lambda e: errors_received.append(e))
        event = _make_event()
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._validation_207([0])
            s.send_events([event])
        assert errors_received
        assert "reject" in str(errors_received[0]).lower()

    def test_partial_failure_error_is_subclass_of_ioerror(self):
        """PartialFailureError must be an IOError for API compatibility."""
        assert issubclass(PartialFailureError, IOError)

    def test_retryable_207_recovers_on_subsequent_success(self):
        """If a retry after a transient 207 returns 200, the batch is sent."""
        s = _make_sender(max_retries=2)
        event = _make_event()
        ok_response = MagicMock()
        ok_response.status_code = 200
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._time"):
            mock_http.post.side_effect = [
                self._bigquery_207([event["event_id"]]),
                ok_response,
            ]
            result = s.send_events([event])
        assert result is True
        assert mock_http.post.call_count == 2

    def test_validation_207_is_not_retried(self):
        """Validation-only 207 fails fast without entering the retry loop."""
        s = _make_sender(max_retries=3, on_error=MagicMock())
        event = _make_event()
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._time"):
            mock_http.post.return_value = self._validation_207([0])
            result = s.send_events([event])
        assert result is False
        assert mock_http.post.call_count == 1
        err = s.on_error.call_args[0][0]
        assert isinstance(err, NonRetryablePartialFailureError)

    def test_mixed_207_accepts_some_and_drops_validation_failures(self):
        """Accepted events count toward on_success; validation failures drop."""
        success_cb = MagicMock()
        error_cb = MagicMock()
        s = _make_sender(max_retries=0, on_success=success_cb, on_error=error_cb)
        events = [_make_event(), _make_event(), _make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._validation_207([1], inserted=2)
            ok, unsent = s._send_events_with_unsent(events)
        assert ok is False  # an event was permanently rejected
        assert unsent == []  # nothing to re-buffer
        success_cb.assert_called_once_with(2)  # the two accepted events
        err = error_cb.call_args[0][0]
        assert isinstance(err, NonRetryablePartialFailureError)

    def test_mixed_207_retries_only_failing_subset(self):
        """A transient 207 re-sends only the failing event, not accepted ones."""
        s = _make_sender(max_retries=1)
        events = [_make_event(), _make_event(), _make_event()]
        failing = events[1]
        ok_response = MagicMock()
        ok_response.status_code = 200
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._time"):
            mock_http.post.side_effect = [
                self._bigquery_207([failing["event_id"]], inserted=2),
                ok_response,
            ]
            result = s.send_events(events)
        assert result is True
        assert mock_http.post.call_count == 2
        # Second POST must contain only the failing event.
        retry_body = json.loads(mock_http.post.call_args_list[1][1]["data"])
        assert len(retry_body["events"]) == 1
        assert retry_body["events"][0]["event_id"] == failing["event_id"]

    def test_207_rebuffers_only_retryable_not_accepted(self):
        """Unsent list contains only the still-failing event after retries."""
        s = _make_sender(max_retries=0)
        events = [_make_event(), _make_event(), _make_event()]
        failing = events[2]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._bigquery_207(
                [failing["event_id"]], inserted=2
            )
            ok, unsent = s._send_events_with_unsent(events)
        assert ok is False
        assert len(unsent) == 1
        assert unsent[0]["event_id"] == failing["event_id"]


# ---------------------------------------------------------------------------
# HTTP 400 — all events rejected (deterministic validation failure)
# ---------------------------------------------------------------------------

class TestSendEvents400Validation:
    """A 400 means every event failed validation — permanent, never retried."""

    def _all_invalid_400(self, count):
        resp = MagicMock()
        resp.status_code = 400
        resp.text = json.dumps({
            "success": False,
            "inserted": 0,
            "failed": count,
            "errors": [
                {"index": i, "event_id": None, "errors": ["event_type is required"]}
                for i in range(count)
            ],
        })
        return resp

    def _structural_400(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.text = json.dumps({"error": "events array must not be empty"})
        return resp

    def test_400_is_not_retried(self):
        s = _make_sender(max_retries=3, on_error=MagicMock())
        events = [_make_event(), _make_event()]
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._time"):
            mock_http.post.return_value = self._all_invalid_400(2)
            result = s.send_events(events)
        assert result is False
        assert mock_http.post.call_count == 1
        err = s.on_error.call_args[0][0]
        assert isinstance(err, NonRetryablePartialFailureError)

    def test_400_events_are_dropped_not_rebuffered(self):
        s = _make_sender(max_retries=0)
        events = [_make_event(), _make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._all_invalid_400(2)
            ok, unsent = s._send_events_with_unsent(events)
        assert ok is False
        assert unsent == []  # permanent failures are not re-buffered

    def test_400_does_not_clog_collector(self):
        s = _make_sender(max_retries=0)
        c = TelemetryCollector()
        c.collect_battery_status(7000, 80.0)
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._all_invalid_400(1)
            result = s.flush_and_send(c)
        assert result is False
        assert c.buffer_size == 0  # invalid event dropped, not restored

    def test_structural_400_is_dropped(self):
        s = _make_sender(max_retries=2)
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http, \
             patch("telemetry.sender._time"):
            mock_http.post.return_value = self._structural_400()
            ok, unsent = s._send_events_with_unsent(events)
        assert ok is False
        assert unsent == []
        assert mock_http.post.call_count == 1


# ---------------------------------------------------------------------------
# Response lifecycle — urequests sockets must be closed
# ---------------------------------------------------------------------------

class TestResponseLifecycle:
    def test_response_closed_after_successful_post(self):
        s = _make_sender()
        resp = MagicMock()
        resp.status_code = 200
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = resp
            s.send_events([_make_event()])
        resp.close.assert_called_once()

    def test_response_closed_on_error_status(self):
        s = _make_sender(max_retries=0)
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "boom"
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = resp
            s.send_events([_make_event()])
        resp.close.assert_called_once()

    def test_missing_close_method_does_not_crash(self):
        s = _make_sender()
        resp = MagicMock(spec=["status_code", "text"])
        resp.status_code = 200
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = resp
            result = s.send_events([_make_event()])
        assert result is True


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
