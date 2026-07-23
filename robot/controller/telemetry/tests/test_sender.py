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
        "endpoint": "https://example.com/unifiedIngress",
        "device_id": "ev3-001",
        "device_token": "test-device-token",
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

    def test_stores_device_id(self):
        s = _make_sender(device_id="ev3-002")
        assert s.device_id == "ev3-002"

    def test_stores_device_token(self):
        s = _make_sender(device_token="secret")
        assert s.device_token == "secret"

    def test_default_batch_size(self):
        s = _make_sender()
        assert s.batch_size == DEFAULT_BATCH_SIZE

    def test_custom_batch_size(self):
        s = _make_sender(batch_size=10)
        assert s.batch_size == 10

    def test_default_max_retries(self):
        s = TelemetrySender(
            endpoint="https://example.com/fn",
            device_id="ev3-001",
            device_token="k",
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

    def test_includes_device_auth_headers(self):
        s = _make_sender(device_id="ev3-007", device_token="my-token")
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            s.send_events(events)
        _, kwargs = mock_http.post.call_args
        headers = kwargs.get("headers", {})
        assert headers.get("X-Device-Id") == "ev3-007"
        assert headers.get("X-Device-Token") == "my-token"

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
# HTTP POST — urequests lacks a `timeout` kwarg (MicroPython compatibility)
# ---------------------------------------------------------------------------

class TestHttpPostTimeoutFallback:
    """Regression: Pybricks MicroPython's bundled ``urequests`` — unlike
    CPython's ``requests`` — does not accept ``timeout`` on ``post()``,
    raising ``TypeError: unexpected keyword argument 'timeout'`` the first
    time telemetry actually sends on-device. Same "unsupported kwarg" shape
    as the ``Thread(daemon=...)`` issue (PEN-188).
    """

    def _mock_response(self, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        return resp

    def test_falls_back_without_timeout_on_typeerror(self):
        s = _make_sender()
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.side_effect = [
                TypeError("post() got an unexpected keyword argument 'timeout'"),
                self._mock_response(200),
            ]
            result = s.send_events(events)
        assert result is True
        assert mock_http.post.call_count == 2

    def test_first_attempt_includes_timeout_second_does_not(self):
        s = _make_sender(timeout=7)
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.side_effect = [
                TypeError("unexpected keyword argument 'timeout'"),
                self._mock_response(200),
            ]
            s.send_events(events)
        first_kwargs = mock_http.post.call_args_list[0][1]
        second_kwargs = mock_http.post.call_args_list[1][1]
        assert first_kwargs.get("timeout") == 7
        assert "timeout" not in second_kwargs

    def test_normal_http_lib_never_triggers_fallback(self):
        """When the HTTP library accepts ``timeout`` (e.g. ``requests``),
        only one call is made — no unnecessary retry."""
        s = _make_sender()
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = self._mock_response(200)
            s.send_events(events)
        assert mock_http.post.call_count == 1

    def test_typeerror_on_both_attempts_is_treated_as_transient_failure(self):
        """If the fallback call also raises TypeError (e.g. a genuinely
        broken HTTP lib), the batch is treated as an ordinary transient
        failure rather than crashing the sender."""
        s = _make_sender(max_retries=0)
        events = [_make_event()]
        with patch("telemetry.sender._http") as mock_http:
            mock_http.post.side_effect = TypeError("still broken")
            result = s.send_events(events)
        assert result is False


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

    def test_async_thread_omits_daemon_kwarg(self):
        """Regression (PEN-188): Thread() must omit the daemon kwarg.

        Pybricks MicroPython's threading.Thread accepts only ``target``/``args``;
        passing ``daemon`` raises TypeError and crashes the app on the EV3.
        """
        s = _make_sender()
        created_kwargs = []

        def capturing_thread(*args, **kwargs):
            created_kwargs.append(kwargs)
            t = MagicMock()
            t.start = MagicMock()
            return t

        with patch("telemetry.sender._threading.Thread", side_effect=capturing_thread):
            s.send_events_async([_make_event()])

        assert len(created_kwargs) == 1, "Expected exactly one Thread to be created"
        assert "daemon" not in created_kwargs[0], (
            "daemon kwarg is unsupported by Pybricks MicroPython Thread()"
        )

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

    def test_overflow_file_not_deleted_before_send_attempt(self):
        """Regression (PEN-221): the overflow file used to be deleted
        unconditionally before the send was even attempted, so a crash
        between the delete and a confirmed successful send would lose those
        events permanently. It must stay on disk, untouched, until the send
        outcome is known.
        """
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            os.remove(path)
            c = TelemetryCollector(max_buffer_size=1, overflow_path=path)
            c.collect_battery_status(7000, 80.0)  # evicted to disk
            c.collect_battery_status(7001, 81.0)  # stays buffered
            assert os.path.exists(path)

            s = _make_sender(max_retries=0)
            with patch("telemetry.sender._http") as mock_http:
                mock_http.post.side_effect = ConnectionError("down")
                result = s.flush_and_send(c)

            assert result is False
            assert os.path.exists(path)
            assert len(c.load_overflow()) == 1
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_overflow_file_cleared_only_after_confirmed_success(self):
        """The overflow file must only be cleared once the send has actually
        succeeded, never on the mere assumption that it will.
        """
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            os.remove(path)
            c = TelemetryCollector(max_buffer_size=1, overflow_path=path)
            c.collect_battery_status(7000, 80.0)  # evicted to disk
            c.collect_battery_status(7001, 81.0)  # stays buffered
            assert os.path.exists(path)

            ok_response = MagicMock()
            ok_response.status_code = 200
            s = _make_sender(batch_size=100)
            with patch("telemetry.sender._http") as mock_http:
                mock_http.post.return_value = ok_response
                result = s.flush_and_send(c)

            assert result is True
            assert not os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_partial_overflow_failure_keeps_only_the_failing_subset_on_disk(self):
        """A partial failure (HTTP 207) must rewrite the overflow file to
        contain only the still-unsent subset, not the whole original set.
        """
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            os.remove(path)
            c = TelemetryCollector(max_buffer_size=1, overflow_path=path)
            c.collect_battery_status(7000, 80.0)  # evicted to disk
            c.collect_battery_status(7001, 81.0)  # evicted to disk
            c.collect_battery_status(7002, 82.0)  # stays buffered
            c.clear()  # drop the buffered one so only the 2 on-disk events matter
            overflow_events = c.load_overflow()
            assert len(overflow_events) == 2
            failing_id = overflow_events[0]["event_id"]
            succeeding_id = overflow_events[1]["event_id"]

            partial_response = MagicMock()
            partial_response.status_code = 207
            partial_response.text = json.dumps({
                "success": False,
                "inserted": 1,
                "failed": 1,
                "errors": [{"event_id": failing_id, "errors": ["backendError"]}],
            })
            s = _make_sender(max_retries=0, batch_size=100)
            with patch("telemetry.sender._http") as mock_http:
                mock_http.post.return_value = partial_response
                result = s.flush_and_send(c)

            assert result is False
            remaining = c.load_overflow()
            assert len(remaining) == 1
            assert remaining[0]["event_id"] == failing_id
            assert succeeding_id not in [e["event_id"] for e in remaining]
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_reconcile_overflow_restores_event_to_memory_when_persist_fails(self):
        """Regression: if clear_overflow() succeeds but re-persisting a
        still-unsent overflow event back to disk then fails, that event
        must be restored to the in-memory buffer rather than silently
        dropped -- the file has already been cleared at that point, so
        "it's still on disk" is no longer a valid fallback.
        """
        s = _make_sender()
        c = TelemetryCollector(overflow_path=None)
        event = _make_event()

        with patch.object(c, "clear_overflow") as mock_clear, \
             patch.object(c, "_persist_to_disk", side_effect=OSError("disk full")) as mock_persist:
            s._reconcile_overflow(c, [event])

        mock_clear.assert_called_once_with()
        mock_persist.assert_called_once_with(event)
        assert c.buffer_size == 1
        assert c.peek()[0]["event_id"] == event["event_id"]

    def test_reconcile_overflow_restores_events_when_collector_cannot_persist(self):
        """If the collector has no ``_persist_to_disk`` hook at all, the
        still-unsent events must be restored to memory rather than silently
        discarded after the file has already been cleared.
        """
        s = _make_sender()
        c = TelemetryCollector(overflow_path=None)
        event = _make_event()

        with patch.object(c, "clear_overflow"), \
             patch.object(TelemetryCollector, "_persist_to_disk", new=None):
            s._reconcile_overflow(c, [event])

        assert c.buffer_size == 1
        assert c.peek()[0]["event_id"] == event["event_id"]

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

    def test_retryable_207_give_up_message_includes_backend_error_detail(self):
        """The final give-up message must surface *why* the endpoint is
        rejecting events (e.g. the BigQuery error reason), not just a bare
        count — otherwise persistent 207s are undiagnosable from the logs.
        """
        errors_received = []
        s = _make_sender(max_retries=0, on_error=lambda e: errors_received.append(e))
        event = _make_event()
        with patch("telemetry.sender._http") as mock_http:
            resp = MagicMock()
            resp.status_code = 207
            resp.text = json.dumps({
                "success": False,
                "inserted": 0,
                "failed": 1,
                "errors": [
                    {"event_id": event["event_id"], "errors": ["no such field: current_ma"]}
                ],
            })
            mock_http.post.return_value = resp
            s.send_events([event])
        assert errors_received
        message = str(errors_received[0])
        assert event["event_id"] in message
        assert "no such field: current_ma" in message

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


# ---------------------------------------------------------------------------
# curl-subprocess HTTPS backend (works around Pybricks urequests' broken TLS
# against Google Cloud Functions — ssl_handshake_status: -256 -> EIO)
# ---------------------------------------------------------------------------

def _fake_curl_run(status_code, response_text="", stderr_text=""):
    """Build a fake replacement for ``telemetry.sender._run_shell_capture``.

    Parses the ``-o '<path>'`` / ``2>'<path>'`` tokens out of the real curl
    command line built by ``_http_post_curl`` and writes to those paths —
    mimicking what curl itself would have written — rather than hardcoding
    the sender's private temp-file naming scheme in the test.
    """
    import re

    def _run(cmd):
        resp_match = re.search(r"-o '([^']*)'", cmd)
        err_match = re.search(r"2>'([^']*)'", cmd)
        if resp_match:
            with open(resp_match.group(1), "w") as fh:
                fh.write(response_text)
        if err_match:
            with open(err_match.group(1), "w") as fh:
                fh.write(stderr_text)
        return str(status_code)

    return _run


class TestShellQuote:
    def test_plain_value_is_wrapped_in_single_quotes(self):
        from telemetry.sender import _shell_quote

        assert _shell_quote("hello") == "'hello'"

    def test_embedded_single_quote_is_escaped(self):
        from telemetry.sender import _shell_quote

        assert _shell_quote("o'brien") == "'o'\"'\"'brien'"

    def test_non_string_value_is_stringified(self):
        from telemetry.sender import _shell_quote

        assert _shell_quote(5) == "'5'"


class TestCurlBackend:
    """``TelemetrySender._http_post_curl`` — the workaround for Pybricks EV3
    MicroPython's ``urequests``/``ussl`` being unable to complete a TLS
    handshake with Google Cloud Functions at all (not just intermittently).
    """

    def test_used_when_http_lib_is_urequests_and_curl_available(self, tmp_path):
        s = _make_sender(curl_temp_dir=str(tmp_path))
        events = [_make_event()]
        with patch("telemetry.sender._HTTP_LIB", "urequests"), \
             patch("telemetry.sender._curl_is_available", return_value=True), \
             patch("telemetry.sender._run_shell_capture", side_effect=_fake_curl_run(200)), \
             patch("telemetry.sender._http") as mock_http:
            result = s.send_events(events)
        assert result is True
        mock_http.post.assert_not_called()

    def test_falls_back_to_urequests_when_curl_unavailable(self, tmp_path):
        s = _make_sender(curl_temp_dir=str(tmp_path))
        events = [_make_event()]
        resp = MagicMock(status_code=200)
        with patch("telemetry.sender._HTTP_LIB", "urequests"), \
             patch("telemetry.sender._curl_is_available", return_value=False), \
             patch("telemetry.sender._run_shell_capture") as mock_shell, \
             patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = resp
            result = s.send_events(events)
        assert result is True
        mock_shell.assert_not_called()
        mock_http.post.assert_called_once()

    def test_requests_lib_never_uses_curl_backend(self, tmp_path):
        """Desktop/CI (``requests`` installed) must be completely unaffected
        by this workaround, even if ``curl`` happens to be on PATH there."""
        s = _make_sender(curl_temp_dir=str(tmp_path))
        events = [_make_event()]
        resp = MagicMock(status_code=200)
        with patch("telemetry.sender._HTTP_LIB", "requests"), \
             patch("telemetry.sender._curl_is_available", return_value=True), \
             patch("telemetry.sender._run_shell_capture") as mock_shell, \
             patch("telemetry.sender._http") as mock_http:
            mock_http.post.return_value = resp
            result = s.send_events(events)
        assert result is True
        mock_shell.assert_not_called()

    def test_response_status_and_body_are_parsed_from_curl_output(self, tmp_path):
        s = _make_sender(curl_temp_dir=str(tmp_path), max_retries=0)
        with patch("telemetry.sender._HTTP_LIB", "urequests"), \
             patch("telemetry.sender._curl_is_available", return_value=True), \
             patch(
                 "telemetry.sender._run_shell_capture",
                 side_effect=_fake_curl_run(207, response_text='{"failed": 1, "errors": []}'),
             ):
            response = s._http_post_curl("{}", {"Content-Type": "application/json"}, 5)
        assert response.status_code == 207
        assert response.text == '{"failed": 1, "errors": []}'

    def test_status_000_raises_oserror_with_stderr_detail(self, tmp_path):
        s = _make_sender(curl_temp_dir=str(tmp_path))
        with patch("telemetry.sender._HTTP_LIB", "urequests"), \
             patch("telemetry.sender._curl_is_available", return_value=True), \
             patch(
                 "telemetry.sender._run_shell_capture",
                 side_effect=_fake_curl_run(0, stderr_text="curl: (35) TLS connect error"),
             ):
            with pytest.raises(OSError, match="TLS connect error"):
                s._http_post_curl("{}", {}, 5)

    def test_status_000_without_stderr_still_raises(self, tmp_path):
        s = _make_sender(curl_temp_dir=str(tmp_path))
        with patch("telemetry.sender._HTTP_LIB", "urequests"), \
             patch("telemetry.sender._curl_is_available", return_value=True), \
             patch("telemetry.sender._run_shell_capture", side_effect=_fake_curl_run(0)):
            with pytest.raises(OSError):
                s._http_post_curl("{}", {}, 5)

    def test_temp_files_are_removed_after_success(self, tmp_path):
        s = _make_sender(curl_temp_dir=str(tmp_path))
        with patch("telemetry.sender._HTTP_LIB", "urequests"), \
             patch("telemetry.sender._curl_is_available", return_value=True), \
             patch("telemetry.sender._run_shell_capture", side_effect=_fake_curl_run(200, "ok")):
            s._http_post_curl("{}", {}, 5)
        assert list(tmp_path.iterdir()) == []

    def test_temp_files_are_removed_after_failure(self, tmp_path):
        s = _make_sender(curl_temp_dir=str(tmp_path))
        with patch("telemetry.sender._HTTP_LIB", "urequests"), \
             patch("telemetry.sender._curl_is_available", return_value=True), \
             patch("telemetry.sender._run_shell_capture", side_effect=_fake_curl_run(0, stderr_text="boom")):
            with pytest.raises(OSError):
                s._http_post_curl("{}", {}, 5)
        assert list(tmp_path.iterdir()) == []

    def test_request_body_is_written_to_temp_file(self, tmp_path):
        """The exact payload curl would upload — verifies the temp file
        actually contains the JSON body at the moment curl "runs", not just
        that a file was written at some point."""
        s = _make_sender(curl_temp_dir=str(tmp_path))
        seen_body = {}

        def _run(cmd):
            import re

            body_match = re.search(r"--data-binary @'([^']*)'", cmd)
            with open(body_match.group(1), "r") as fh:
                seen_body["content"] = fh.read()
            resp_match = re.search(r"-o '([^']*)'", cmd)
            with open(resp_match.group(1), "w") as fh:
                fh.write("")
            return "200"

        with patch("telemetry.sender._HTTP_LIB", "urequests"), \
             patch("telemetry.sender._curl_is_available", return_value=True), \
             patch("telemetry.sender._run_shell_capture", side_effect=_run):
            s._http_post_curl('{"events": []}', {}, 5)
        assert seen_body["content"] == '{"events": []}'

    def test_device_headers_are_passed_as_curl_dash_h_args(self, tmp_path):
        s = _make_sender(
            curl_temp_dir=str(tmp_path), device_id="ev3-001", device_token="secret-token"
        )
        seen_cmd = {}

        def _run(cmd):
            seen_cmd["cmd"] = cmd
            return _fake_curl_run(200)(cmd)

        with patch("telemetry.sender._HTTP_LIB", "urequests"), \
             patch("telemetry.sender._curl_is_available", return_value=True), \
             patch("telemetry.sender._run_shell_capture", side_effect=_run):
            s._http_post_curl(
                "{}", {"X-Device-Id": "ev3-001", "X-Device-Token": "secret-token"}, 5
            )
        assert "X-Device-Id: ev3-001" in seen_cmd["cmd"]
        assert "X-Device-Token: secret-token" in seen_cmd["cmd"]

    def test_curl_availability_check_is_cached(self):
        import telemetry.sender as sender_module

        sender_module._CURL_AVAILABLE = None
        with patch("telemetry.sender._run_shell_capture", return_value="/usr/bin/curl") as mock_shell:
            first = sender_module._curl_is_available()
            second = sender_module._curl_is_available()
        assert first is True
        assert second is True
        mock_shell.assert_called_once()
        sender_module._CURL_AVAILABLE = None  # reset for other tests

    def test_curl_availability_false_when_not_on_path(self):
        import telemetry.sender as sender_module

        sender_module._CURL_AVAILABLE = None
        with patch("telemetry.sender._run_shell_capture", return_value=""):
            result = sender_module._curl_is_available()
        assert result is False
        sender_module._CURL_AVAILABLE = None  # reset for other tests
