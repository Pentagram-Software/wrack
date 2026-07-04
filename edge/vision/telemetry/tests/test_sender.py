"""Unit tests for telemetry/sender.py (Raspberry Pi telemetry module, PEN-166)."""

import io
import json
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from telemetry.collector import RpiTelemetryCollector
from telemetry.sender import (
    DEFAULT_BATCH_SIZE,
    NonRetryablePartialFailureError,
    PartialFailureError,
    RpiTelemetrySender,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uid() -> str:
    return str(uuid.uuid4())


def _make_event(event_type: str = "connection_status") -> dict:
    return {
        "event_id": _uid(),
        "event_type": event_type,
        "source": "rpi",
        "timestamp": _ts(),
        "payload": {"connected": True},
    }


def _make_sender(**kwargs) -> RpiTelemetrySender:
    defaults = {
        "endpoint": "https://example.com/telemetryIngestion",
        "api_key": "test-api-key",
        "max_retries": 0,
        "timeout": 5,
    }
    defaults.update(kwargs)
    return RpiTelemetrySender(**defaults)


def _mock_response(status_code=200, body="{}"):
    resp = MagicMock()
    resp.status = status_code
    resp.read.return_value = body.encode("utf-8")
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(status_code=500, body="server error"):
    return HTTPError(
        url="https://example.com/telemetryIngestion",
        code=status_code,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(body.encode("utf-8")),
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_stores_endpoint(self):
        s = _make_sender(endpoint="https://my.endpoint/fn")
        assert s.endpoint == "https://my.endpoint/fn"

    def test_default_batch_size(self):
        s = _make_sender()
        assert s.batch_size == DEFAULT_BATCH_SIZE

    def test_custom_batch_size(self):
        s = _make_sender(batch_size=10)
        assert s.batch_size == 10

    def test_rejects_zero_batch_size(self):
        with pytest.raises(ValueError):
            _make_sender(batch_size=0)

    def test_rejects_negative_max_retries(self):
        with pytest.raises(ValueError):
            _make_sender(max_retries=-1)

    def test_missing_endpoint_raises_value_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                RpiTelemetrySender()

    def test_endpoint_from_env_var(self):
        with patch.dict(os.environ, {"TELEMETRY_ENDPOINT": "https://env.example/fn"}, clear=True):
            s = RpiTelemetrySender()
            assert s.endpoint == "https://env.example/fn"

    def test_api_key_from_env_var(self):
        with patch.dict(
            os.environ,
            {"TELEMETRY_ENDPOINT": "https://env.example/fn", "TELEMETRY_API_KEY": "env-key"},
            clear=True,
        ):
            s = RpiTelemetrySender()
            assert s.api_key == "env-key"

    def test_batch_size_from_env_var(self):
        with patch.dict(
            os.environ,
            {"TELEMETRY_ENDPOINT": "https://env.example/fn", "TELEMETRY_BATCH_SIZE": "17"},
            clear=True,
        ):
            s = RpiTelemetrySender()
            assert s.batch_size == 17

    def test_flush_interval_default(self):
        s = _make_sender()
        assert s.flush_interval == 30.0

    def test_flush_interval_from_env_var(self):
        with patch.dict(
            os.environ,
            {"TELEMETRY_ENDPOINT": "https://env.example/fn", "TELEMETRY_FLUSH_INTERVAL": "5"},
            clear=True,
        ):
            s = RpiTelemetrySender()
            assert s.flush_interval == 5.0


# ---------------------------------------------------------------------------
# send_events - success paths
# ---------------------------------------------------------------------------

class TestSendEventsSuccess:
    def test_returns_true_for_empty_list(self):
        s = _make_sender()
        assert s.send_events([]) is True

    def test_no_http_call_for_empty_list(self):
        s = _make_sender()
        with patch("telemetry.sender.urllib_request.urlopen") as mock_urlopen:
            s.send_events([])
        mock_urlopen.assert_not_called()

    def test_returns_true_on_200(self):
        s = _make_sender()
        with patch("telemetry.sender.urllib_request.urlopen", return_value=_mock_response(200)):
            assert s.send_events([_make_event()]) is True

    def test_posts_json_body_with_events_key(self):
        s = _make_sender()
        with patch("telemetry.sender.urllib_request.urlopen", return_value=_mock_response(200)) as mock_urlopen:
            s.send_events([_make_event()])
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data)
        assert "events" in body
        assert len(body["events"]) == 1

    def test_includes_api_key_header(self):
        s = _make_sender(api_key="my-key")
        with patch("telemetry.sender.urllib_request.urlopen", return_value=_mock_response(200)) as mock_urlopen:
            s.send_events([_make_event()])
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("X-api-key") == "my-key"

    def test_on_success_callback_called_with_count(self):
        callback = MagicMock()
        s = _make_sender(on_success=callback)
        with patch("telemetry.sender.urllib_request.urlopen", return_value=_mock_response(200)):
            s.send_events([_make_event(), _make_event()])
        callback.assert_called_once_with(2)


# ---------------------------------------------------------------------------
# send_events - batching
# ---------------------------------------------------------------------------

class TestBatching:
    def test_splits_into_multiple_batches(self):
        s = _make_sender(batch_size=2)
        events = [_make_event() for _ in range(5)]
        with patch("telemetry.sender.urllib_request.urlopen", return_value=_mock_response(200)) as mock_urlopen:
            s.send_events(events)
        assert mock_urlopen.call_count == 3  # 2 + 2 + 1


# ---------------------------------------------------------------------------
# send_events - transient failure / retry
# ---------------------------------------------------------------------------

class TestRetry:
    def test_returns_false_on_persistent_500(self):
        s = _make_sender(max_retries=0)
        with patch("telemetry.sender.urllib_request.urlopen", side_effect=_http_error(500)), \
             patch("telemetry.sender._time"):
            assert s.send_events([_make_event()]) is False

    def test_retries_up_to_max_retries(self):
        s = _make_sender(max_retries=2)
        with patch("telemetry.sender.urllib_request.urlopen", side_effect=_http_error(500)) as mock_urlopen, \
             patch("telemetry.sender._time"):
            s.send_events([_make_event()])
        assert mock_urlopen.call_count == 3  # initial + 2 retries

    def test_recovers_on_subsequent_success(self):
        s = _make_sender(max_retries=2)
        with patch(
            "telemetry.sender.urllib_request.urlopen",
            side_effect=[_http_error(500), _mock_response(200)],
        ), patch("telemetry.sender._time"):
            assert s.send_events([_make_event()]) is True

    def test_connection_error_is_retried(self):
        s = _make_sender(max_retries=1)
        with patch(
            "telemetry.sender.urllib_request.urlopen",
            side_effect=[URLError("connection refused"), _mock_response(200)],
        ), patch("telemetry.sender._time"):
            assert s.send_events([_make_event()]) is True

    def test_400_is_not_retried(self):
        s = _make_sender(max_retries=3)
        with patch(
            "telemetry.sender.urllib_request.urlopen",
            return_value=_mock_response(400),
        ) as mock_urlopen:
            s.send_events([_make_event()])
        assert mock_urlopen.call_count == 1

    def test_on_error_called_on_final_failure(self):
        error_cb = MagicMock()
        s = _make_sender(max_retries=0, on_error=error_cb)
        with patch("telemetry.sender.urllib_request.urlopen", side_effect=_http_error(500)), \
             patch("telemetry.sender._time"):
            s.send_events([_make_event()])
        error_cb.assert_called_once()


# ---------------------------------------------------------------------------
# HTTP 207 partial failure
# ---------------------------------------------------------------------------

class TestPartial207:
    def _validation_207(self, indices, inserted=0):
        return _mock_response(
            207,
            json.dumps({
                "success": False,
                "inserted": inserted,
                "failed": len(indices),
                "errors": [
                    {"index": i, "event_id": None, "errors": ["event_type is required"]}
                    for i in indices
                ],
            }),
        )

    def _bigquery_207(self, event_ids, inserted=0):
        return _mock_response(
            207,
            json.dumps({
                "success": False,
                "inserted": inserted,
                "failed": len(event_ids),
                "errors": [{"event_id": eid, "errors": ["backendError"]} for eid in event_ids],
            }),
        )

    def test_validation_failure_is_permanent_not_retried(self):
        s = _make_sender(max_retries=3)
        with patch(
            "telemetry.sender.urllib_request.urlopen",
            return_value=self._validation_207([0]),
        ) as mock_urlopen:
            result = s.send_events([_make_event()])
        assert result is False
        assert mock_urlopen.call_count == 1

    def test_validation_failure_error_callback(self):
        error_cb = MagicMock()
        s = _make_sender(max_retries=0, on_error=error_cb)
        with patch(
            "telemetry.sender.urllib_request.urlopen",
            return_value=self._validation_207([0]),
        ):
            s.send_events([_make_event()])
        exc = error_cb.call_args[0][0]
        assert isinstance(exc, NonRetryablePartialFailureError)

    def test_retryable_207_is_retried(self):
        event = _make_event()
        s = _make_sender(max_retries=2)
        with patch(
            "telemetry.sender.urllib_request.urlopen",
            return_value=self._bigquery_207([event["event_id"]]),
        ) as mock_urlopen, patch("telemetry.sender._time"):
            result = s.send_events([event])
        assert result is False
        assert mock_urlopen.call_count == 3  # initial + 2 retries

    def test_retryable_207_recovers_on_subsequent_200(self):
        event = _make_event()
        s = _make_sender(max_retries=2)
        with patch(
            "telemetry.sender.urllib_request.urlopen",
            side_effect=[self._bigquery_207([event["event_id"]]), _mock_response(200)],
        ), patch("telemetry.sender._time"):
            assert s.send_events([event]) is True

    def test_give_up_message_includes_backend_error_detail(self):
        event = _make_event()
        errors_received = []
        s = _make_sender(max_retries=0, on_error=lambda e: errors_received.append(e))
        with patch(
            "telemetry.sender.urllib_request.urlopen",
            return_value=self._bigquery_207([event["event_id"]]),
        ):
            s.send_events([event])
        assert errors_received
        message = str(errors_received[0])
        assert event["event_id"] in message
        assert "backendError" in message

    def test_partial_failure_error_is_subclass_of_oserror(self):
        assert issubclass(PartialFailureError, OSError)


# ---------------------------------------------------------------------------
# send_events_async
# ---------------------------------------------------------------------------

class TestSendEventsAsync:
    def test_returns_immediately(self):
        s = _make_sender()
        with patch("telemetry.sender.urllib_request.urlopen", return_value=_mock_response(200)):
            s.send_events_async([_make_event()])  # must not block/raise

    def test_noop_for_empty_list(self):
        s = _make_sender()
        with patch("telemetry.sender.urllib_request.urlopen") as mock_urlopen:
            s.send_events_async([])
        mock_urlopen.assert_not_called()


# ---------------------------------------------------------------------------
# flush_and_send
# ---------------------------------------------------------------------------

class TestFlushAndSend:
    def test_sends_buffered_events(self):
        c = RpiTelemetryCollector(overflow_path=None)
        c.collect("connection_status", connected=True)
        s = _make_sender()
        with patch("telemetry.sender.urllib_request.urlopen", return_value=_mock_response(200)):
            result = s.flush_and_send(c)
        assert result is True
        assert c.buffer_size == 0

    def test_true_for_empty_collector(self):
        c = RpiTelemetryCollector()
        s = _make_sender()
        with patch("telemetry.sender.urllib_request.urlopen") as mock_urlopen:
            result = s.flush_and_send(c)
        assert result is True
        mock_urlopen.assert_not_called()

    def test_restores_events_to_collector_on_failure(self):
        c = RpiTelemetryCollector(overflow_path=None)
        c.collect("connection_status", connected=True)
        s = _make_sender(max_retries=0)
        with patch("telemetry.sender.urllib_request.urlopen", side_effect=_http_error(500)), \
             patch("telemetry.sender._time"):
            result = s.flush_and_send(c)
        assert result is False
        assert c.buffer_size == 1
