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

# ``typing`` is unavailable on Pybricks/MicroPython.  Annotations are strings
# (``from __future__ import annotations``) so the names are never evaluated at
# runtime; the fallback simply lets the module import on the EV3.
try:
    from typing import Any, Callable, Dict, List, Optional
except ImportError:  # pragma: no cover - MicroPython runtime path
    Any = Callable = Dict = List = Optional = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------

try:
    import time as _time
    _HAS_TIME = True
except ImportError:
    _HAS_TIME = False

# ``threading`` is unavailable on some Pybricks/MicroPython builds.  Guard it so
# importing the telemetry package never fails on the EV3; async sends fall back
# to a synchronous send when threads are not available.
try:
    import threading as _threading
    _HAS_THREADING = True
except ImportError:
    _threading = None  # type: ignore[assignment]
    _HAS_THREADING = False

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
    """HTTP 207 Multi-Status — some events in the batch were not stored.

    Surfaced via the ``on_error`` callback when, after all retries, one or
    more events from a 207 response are still failing.  Only the events that
    keep failing are reported / re-buffered; events the endpoint accepted are
    never re-sent.

    Retryable 207 failures (e.g. transient BigQuery streaming errors) are
    re-sent with only the failing subset.  Because ``telemetry.js`` passes
    each row's ``event_id`` as the BigQuery ``insertId``, any row that was
    already accepted within the streaming buffer (~1-minute window) is
    de-duplicated rather than written twice, so resending is safe.
    """


class NonRetryablePartialFailureError(PartialFailureError):
    """HTTP 207 failure for events that will never succeed on retry.

    Raised for permanent validation failures (the endpoint reports these
    with an ``index`` field referencing the rejected event's position in the
    batch).  These events are dropped rather than re-buffered, since
    re-sending the same payload would fail identically.
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
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
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
        ok, _unsent = self._send_events_with_unsent(events)
        return ok

    def send_events_async(
        self,
        events: List[Dict[str, Any]],
        *,
        collector: Optional[Any] = None,
    ) -> None:
        """Send *events* in a background daemon thread (fire-and-forget).

        Returns immediately.  Use :attr:`on_success` / :attr:`on_error`
        callbacks to observe the result.

        When ``threading`` is unavailable (some MicroPython builds) the send
        runs synchronously so events are never silently dropped.
        """
        if not events:
            return
        if not _HAS_THREADING:
            # No threads on this runtime — fall back to a blocking send rather
            # than dropping the events.
            self._async_worker(list(events), collector)
            return
        t = _threading.Thread(
            target=self._async_worker,
            args=(list(events), collector),
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
    ) -> tuple[bool, List[Dict[str, Any]]]:
        """Send *batch* with retries, returning ``(fully_ok, unsent_events)``.

        ``fully_ok`` is ``True`` only when every event in *batch* was stored
        (no permanent rejections and nothing left failing).  ``unsent_events``
        contains just the events that should be re-buffered and retried later;
        events the endpoint accepted, and permanently-rejected (validation)
        events, are never included.

        On an HTTP 207 the response body is parsed per-event: validation
        failures (which carry an ``index``) are dropped as permanent, while
        transient BigQuery failures (which carry an ``event_id``) are resent
        with only the failing subset.  Resending is safe because the endpoint
        sets each row's ``insertId`` to its ``event_id``, so BigQuery
        de-duplicates any already-accepted row.
        """
        current = list(batch)
        wait = DEFAULT_RETRY_BASE_S
        had_permanent = False

        for attempt in range(self.max_retries + 1):
            try:
                accepted, permanent, retryable = self._post_batch(current)
            except Exception as exc:  # noqa: BLE001 — network / non-2xx HTTP
                if attempt < self.max_retries:
                    if _HAS_TIME:
                        _time.sleep(wait)
                    wait *= 2
                    continue
                self._fire_error(exc)
                return False, list(current)

            if accepted and self.on_success:
                self.on_success(len(accepted))

            if permanent:
                had_permanent = True
                self._fire_error(
                    NonRetryablePartialFailureError(
                        f"telemetry endpoint permanently rejected "
                        f"{len(permanent)} event(s) (validation failure, "
                        f"not retried)"
                    )
                )

            if not retryable:
                return (not had_permanent), []

            if attempt < self.max_retries:
                current = retryable
                if _HAS_TIME:
                    _time.sleep(wait)
                wait *= 2
                continue

            self._fire_error(
                PartialFailureError(
                    f"HTTP 207 partial failure: {len(retryable)} event(s) "
                    f"still failing after {self.max_retries} retries"
                )
            )
            return False, list(retryable)

        return False, list(current)

    def _send_events_with_unsent(
        self,
        events: List[Dict[str, Any]],
    ) -> tuple[bool, List[Dict[str, Any]]]:
        """Send *events* in batches, returning ``(all_ok, unsent_events)``.

        ``unsent_events`` holds only the events that still need to be retried
        later (accepted and permanently-rejected events are excluded).  If a
        batch fails in its entirety (e.g. the endpoint is unreachable), the
        remaining un-attempted events are treated as unsent and the loop stops
        early to avoid hammering a down endpoint.
        """
        if not events:
            return True, []

        if _http is None:
            print(
                "[TelemetrySender] WARNING: No HTTP library available "
                "(install 'requests'). Cannot send telemetry."
            )
            return False, list(events)

        all_ok = True
        unsent: List[Dict[str, Any]] = []
        batch_start = 0
        total = len(events)

        while batch_start < total:
            batch = events[batch_start : batch_start + self.batch_size]
            fully_ok, batch_unsent = self._send_batch_with_retry(batch)
            if not fully_ok:
                all_ok = False
            unsent.extend(batch_unsent)

            # Whole batch unsent → likely a transient/endpoint-wide failure.
            # Stop sending and treat the remainder as unsent.
            if batch_unsent and len(batch_unsent) == len(batch):
                unsent.extend(events[batch_start + self.batch_size :])
                return False, unsent

            batch_start += self.batch_size

        return all_ok, unsent

    def _post_batch(
        self, batch: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Execute a single HTTP POST for *batch*.

        Returns a ``(accepted, permanent, retryable)`` tuple of event lists:

        * **2xx** — every event accepted.
        * **207** — classified per-event by :meth:`_classify_207`.
        * **400** — a deterministic client/validation error; every event is
          permanent (dropped + reported), since re-sending the same payload
          would fail identically.
        * anything else (5xx, transport errors) raises so the caller applies
          transient-failure retry/back-off.

        The response is always closed in a ``finally`` block — on Pybricks the
        ``urequests`` response owns the underlying socket, so failing to close
        it leaks sockets/RAM across repeated telemetry flushes.

        Raises
        ------
        IOError
            Any non-2xx, non-207, non-400 HTTP status.
        Exception
            Transport errors from the underlying HTTP library.
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

        # Read everything we need from the response, then always close it.
        try:
            status = getattr(response, "status_code", None)
            if status is None:
                # urequests uses .status_code too, but guard anyway
                status = getattr(response, "status", None)
            body_text = getattr(response, "text", "") or ""
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 — close must never crash a send
                    pass

        if status is None:
            # Cannot determine status — assume the batch was accepted.
            return list(batch), [], []

        status_int = int(status)

        if status_int == 207:
            return self._classify_207(batch, body_text)

        if 200 <= status_int < 300:
            return list(batch), [], []

        if status_int == 400:
            # Deterministic client/validation error — never retry.  The
            # all-invalid path returns per-event errors; structural request
            # errors have none.  Either way no event can succeed on retry.
            return [], list(batch), []

        raise IOError(
            f"HTTP {status} from telemetry endpoint: {str(body_text)[:200]}"
        )

    def _async_worker(
        self,
        events: List[Dict[str, Any]],
        collector: Optional[Any] = None,
    ) -> None:
        """Thread target for :meth:`send_events_async`."""
        ok, unsent = self._send_events_with_unsent(events)
        if not ok and collector is not None:
            self._restore_events_to_collector(collector, unsent)

    def _fire_error(self, exc: Exception) -> None:
        """Invoke the ``on_error`` callback, or log if none is registered."""
        if self.on_error:
            self.on_error(exc)
        else:
            print(f"[TelemetrySender] ERROR: {exc}")

    def _classify_207(
        self, batch: List[Dict[str, Any]], response_text: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Split a 207 batch into ``(accepted, permanent, retryable)``.

        The Cloud Function (``telemetry.js``) reports each failed event in an
        ``errors`` list.  Validation failures carry an ``index`` (the event's
        position in the batch) and are permanent.  BigQuery streaming failures
        carry the ``event_id`` and are retryable.  Anything not reported as a
        failure was accepted.

        If the body cannot be parsed, or reports more failures than we can map
        to events, we conservatively treat the unmapped events as retryable
        (re-sending is safe thanks to ``insertId`` de-duplication).
        """
        if not response_text:
            return [], [], list(batch)
        try:
            payload = json.loads(response_text)
        except (TypeError, ValueError):
            return [], [], list(batch)

        errors = payload.get("errors") if isinstance(payload, dict) else None
        if not isinstance(errors, list) or not errors:
            return [], [], list(batch)

        permanent_indices = set()
        retryable_ids = set()
        for err in errors:
            if not isinstance(err, dict):
                continue
            idx = err.get("index")
            if isinstance(idx, int) and 0 <= idx < len(batch):
                permanent_indices.add(idx)
                continue
            event_id = err.get("event_id")
            if event_id:
                retryable_ids.add(event_id)

        accepted: List[Dict[str, Any]] = []
        permanent: List[Dict[str, Any]] = []
        retryable: List[Dict[str, Any]] = []
        for i, event in enumerate(batch):
            if i in permanent_indices:
                permanent.append(event)
            elif event.get("event_id") in retryable_ids:
                retryable.append(event)
            else:
                accepted.append(event)

        # Defensive: if the endpoint reported more failures than we could map,
        # retry the accepted remainder too rather than silently dropping them.
        reported_failed = payload.get("failed")
        if (
            isinstance(reported_failed, int)
            and reported_failed > len(permanent) + len(retryable)
        ):
            retryable = retryable + accepted
            accepted = []

        return accepted, permanent, retryable

    # ------------------------------------------------------------------
    # Convenience: flush collector and send
    # ------------------------------------------------------------------

    def flush_and_send(self, collector: Any, *, async_send: bool = False) -> Optional[bool]:
        """Flush *collector* and send all collected events.

        This drains both the on-disk overflow file (oldest events, persisted
        when the in-memory buffer overflowed) and the in-memory buffer, sending
        the overflow events first to preserve ordering.  The overflow file is
        cleared once its events have been taken into memory; any event that
        ultimately fails to send is restored to the collector (and re-persisted
        on overflow), so nothing is silently lost or sent twice.

        Parameters
        ----------
        collector:
            A :class:`telemetry.collector.TelemetryCollector` instance.
        async_send:
            If ``True`` use :meth:`send_events_async` (non-blocking).

        Returns
        -------
        bool or None
            ``True``/``False`` result of the send, or ``None`` when
            *async_send* is ``True``.
        """
        overflow_events = self._drain_overflow(collector)
        events = overflow_events + collector.flush()
        if not events:
            return True
        if async_send:
            self.send_events_async(events, collector=collector)
            return None
        ok, unsent = self._send_events_with_unsent(events)
        if not ok:
            self._restore_events_to_collector(collector, unsent)
        return ok

    def _drain_overflow(self, collector: Any) -> List[Dict[str, Any]]:
        """Load persisted overflow events and clear the overflow file.

        Best-effort: the events are taken into memory so they can be sent
        alongside the in-memory buffer.  Clearing the file up front means a
        send failure re-persists only the events that still need retrying
        (via :meth:`_restore_events_to_collector`), avoiding duplicate sends.
        Returns ``[]`` if the collector has no overflow support.
        """
        load = getattr(collector, "load_overflow", None)
        if not callable(load):
            return []
        try:
            events = load() or []
        except Exception:  # noqa: BLE001 — overflow drain must never crash a send
            return []
        if events:
            clear = getattr(collector, "clear_overflow", None)
            if callable(clear):
                try:
                    clear()
                except Exception:  # noqa: BLE001
                    pass
        return list(events)

    def _restore_events_to_collector(
        self,
        collector: Any,
        events: List[Dict[str, Any]],
    ) -> None:
        """Best-effort restore of flushed events after failed send.

        If the collector exposes ``_buffer_event`` we replay through it so
        existing overflow / eviction behavior is preserved.
        """
        if not events:
            return
        buffer_event = getattr(collector, "_buffer_event", None)
        if callable(buffer_event):
            for event in events:
                buffer_event(event)
