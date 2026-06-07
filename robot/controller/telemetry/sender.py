"""
Telemetry event sender for the EV3 robot controller.

Responsible for:
- Sending batches of telemetry event dicts to the Cloud Function ingestion
  endpoint via HTTP POST.
- Retrying failed requests with exponential back-off (up to
  ``max_retries`` attempts).
- Operating fire-and-forget in a background thread when ``threaded=True``
  so the robot control loop is never blocked.

HTTP library selection
----------------------
The module tries to import the standard ``requests`` library first (CPython /
desktop / Raspberry Pi environments).  On Pybricks MicroPython it falls back
to the ``urequests`` module bundled with Pybricks, which exposes the same
minimal API.  If neither is available, ``send_events()`` returns ``False``
and logs a warning to stdout.

Usage::

    from telemetry.sender import TelemetrySender

    sender = TelemetrySender(
        endpoint="https://europe-central2-wrack-control.cloudfunctions.net/telemetryIngestion",
        api_key="your-secret-api-key",
    )
    result = sender.send_events(events)   # list of event dicts
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------

try:
    import time as _time
    _HAS_TIME = True
except ImportError:
    _HAS_TIME = False

# HTTP library — prefer ``requests`` (CPython), fall back to ``urequests``
# (MicroPython/Pybricks), fail gracefully if neither is present.
try:
    import requests as _http  # type: ignore[import]
    _HTTP_LIB = "requests"
except ImportError:
    try:
        import urequests as _http  # type: ignore[import]
        _HTTP_LIB = "urequests"
    except ImportError:
        _http = None  # type: ignore[assignment]
        _HTTP_LIB = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_S = 10
DEFAULT_RETRY_BASE_S = 1.0  # first retry wait; doubles each attempt

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PartialFailureError(IOError):
    """HTTP 207 Multi-Status — partial batch accepted, do NOT retry.

    Raised by :meth:`TelemetrySender._post_batch` when the Cloud Function
    returns 207.  The endpoint (``telemetry.js``) inserts rows via
    ``table.insert(rows)`` *without* ``insertId``, so retrying the whole
    batch would duplicate the rows that were already accepted.  The failed
    events are either schema-invalid (permanently un-insertable) or hit a
    transient BigQuery error for that specific row; either way, resending
    the full batch is unsafe and is not retried.
    """


# ---------------------------------------------------------------------------
# TelemetrySender
# ---------------------------------------------------------------------------


class TelemetrySender:
    """Send telemetry events to the Cloud Function ingestion endpoint.

    Parameters
    ----------
    endpoint:
        Full HTTPS URL of the ``telemetryIngestion`` Cloud Function.
    api_key:
        API key sent in the ``X-API-Key`` request header.
    batch_size:
        Maximum number of events per HTTP request.
    max_retries:
        Number of retry attempts after a transient failure (before giving up).
    timeout:
        HTTP request timeout in seconds.
    threaded:
        When ``True``, :meth:`send_events_async` can be used to send in a
        background daemon thread.
    on_success:
        Optional callback invoked with ``(sent_count: int)`` on success.
    on_error:
        Optional callback invoked with ``(error: Exception)`` on final failure.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: int = DEFAULT_TIMEOUT_S,
        threaded: bool = False,
        on_success: Optional[Callable[[int], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.timeout = timeout
        self.threaded = threaded
        self.on_success = on_success
        self.on_error = on_error

    # ------------------------------------------------------------------
    # Public send interface
    # ------------------------------------------------------------------

    def send_events(self, events: List[Dict[str, Any]]) -> bool:
        """Send *events* to the ingestion endpoint, batching as needed.

        Events are split into chunks of at most :attr:`batch_size` and sent
        in sequence.  Each chunk is retried up to :attr:`max_retries` times
        on transient failure.

        Parameters
        ----------
        events:
            List of event envelope dicts (as produced by
            :class:`telemetry.collector.TelemetryCollector`).

        Returns
        -------
        bool
            ``True`` if all chunks were sent successfully; ``False`` if any
            chunk ultimately failed after all retries.
        """
        if not events:
            return True

        if _http is None:
            print(
                "[TelemetrySender] WARNING: No HTTP library available "
                "(install 'requests'). Cannot send telemetry."
            )
            return False

        all_ok = True
        for batch in self._batches(events):
            ok = self._send_batch_with_retry(batch)
            if not ok:
                all_ok = False

        return all_ok

    def send_events_async(self, events: List[Dict[str, Any]]) -> None:
        """Send *events* in a background daemon thread (fire-and-forget).

        Returns immediately.  Use :attr:`on_success` / :attr:`on_error`
        callbacks to observe the result.
        """
        if not events:
            return
        t = threading.Thread(
            target=self._async_worker,
            args=(list(events),),
            daemon=True,
        )
        t.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _batches(
        self, events: List[Dict[str, Any]]
    ):
        """Yield successive slices of *events* of length :attr:`batch_size`."""
        for i in range(0, len(events), self.batch_size):
            yield events[i : i + self.batch_size]

    def _send_batch_with_retry(
        self, batch: List[Dict[str, Any]]
    ) -> bool:
        """Attempt to send *batch* with exponential back-off retries.

        Returns ``True`` on success, ``False`` after all retries are
        exhausted.  A :exc:`PartialFailureError` (HTTP 207) is never
        retried because the Cloud Function does not use ``insertId`` and
        retrying would duplicate already-accepted rows.
        """
        last_exc: Optional[Exception] = None
        wait = DEFAULT_RETRY_BASE_S

        for attempt in range(self.max_retries + 1):
            try:
                self._post_batch(batch)
                if self.on_success:
                    self.on_success(len(batch))
                return True
            except PartialFailureError as exc:
                last_exc = exc
                break  # do not retry — would duplicate already-inserted rows
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.max_retries:
                    if _HAS_TIME:
                        _time.sleep(wait)
                    wait *= 2

        if self.on_error and last_exc is not None:
            self.on_error(last_exc)
        else:
            print(
                f"[TelemetrySender] ERROR: Failed to send batch of "
                f"{len(batch)} events after {self.max_retries} retries: "
                f"{last_exc}"
            )
        return False

    def _post_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Execute a single HTTP POST for *batch*.

        Raises
        ------
        PartialFailureError
            HTTP 207 Multi-Status: the Cloud Function accepted some events
            but rejected others.  The caller must NOT retry — ``telemetry.js``
            inserts rows without ``insertId``, so resending the whole batch
            would duplicate the already-accepted rows.
        IOError
            Any other network or non-2xx HTTP error (caller handles retries).
        """
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        body = json.dumps({"events": batch})

        response = _http.post(  # type: ignore[union-attr]
            self.endpoint,
            data=body,
            headers=headers,
            timeout=self.timeout,
        )

        status = getattr(response, "status_code", None)
        if status is None:
            # urequests uses .status_code too, but guard anyway
            status = getattr(response, "status", None)

        if status is not None:
            status_int = int(status)

            if status_int == 207:
                # Partial failure: some events were accepted, some were not.
                # Do NOT retry — the endpoint has no insertId deduplication,
                # so retrying would create duplicate rows for accepted events.
                body_text = getattr(response, "text", "") or ""
                raise PartialFailureError(
                    f"HTTP 207 partial failure from telemetry endpoint "
                    f"(some events rejected): {body_text[:300]}"
                )

            if not (200 <= status_int < 300):
                raise IOError(
                    f"HTTP {status} from telemetry endpoint: "
                    f"{getattr(response, 'text', '')[:200]}"
                )

    def _async_worker(self, events: List[Dict[str, Any]]) -> None:
        """Thread target for :meth:`send_events_async`."""
        self.send_events(events)

    # ------------------------------------------------------------------
    # Convenience: flush collector and send
    # ------------------------------------------------------------------

    def flush_and_send(self, collector: Any, *, async_send: bool = False) -> Optional[bool]:
        """Flush *collector*'s buffer and send all collected events.

        Parameters
        ----------
        collector:
            A :class:`telemetry.collector.TelemetryCollector` instance.
        async_send:
            If ``True`` use :meth:`send_events_async` (non-blocking).

        Returns
        -------
        bool or None
            ``True``/``False`` result of :meth:`send_events`, or ``None``
            when *async_send* is ``True``.
        """
        events = collector.flush()
        if not events:
            return True
        if async_send:
            self.send_events_async(events)
            return None
        return self.send_events(events)
