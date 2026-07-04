"""
Telemetry event sender for the Raspberry Pi vision/analytics module (PEN-166).

Standalone counterpart to ``robot/controller/telemetry/sender.py``. Uses the
standard-library ``urllib`` for HTTP — matching the convention already
established in ``edge/video-streamer/telemetry.py`` (which avoids adding
``requests`` as a project dependency) — rather than the EV3 module's
requests/urequests dual fallback; there is no MicroPython constraint here.

Responsible for:
- Sending batches of telemetry event dicts to the Cloud Function ingestion
  endpoint via HTTP POST.
- Retrying failed requests with exponential back-off (up to
  ``max_retries`` attempts).
- Operating fire-and-forget in a background thread when ``threaded=True``
  so the caller is never blocked.

Usage::

    from telemetry.sender import RpiTelemetrySender

    sender = RpiTelemetrySender(
        endpoint="https://europe-central2-wrack-control.cloudfunctions.net/telemetryIngestion",
        api_key="your-secret-api-key",
    )
    result = sender.send_events(events)   # list of event dicts
"""

from __future__ import annotations

import json
import os
import threading
import time as _time
from typing import Any, Callable, Dict, List, Optional
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_S = 10
DEFAULT_RETRY_BASE_S = 1.0  # first retry wait; doubles each attempt
DEFAULT_FLUSH_INTERVAL_S = 30  # for a future periodic-loop caller to read

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PartialFailureError(OSError):
    """HTTP 207 Multi-Status — some events in the batch were not stored.

    Surfaced via the ``on_error`` callback when, after all retries, one or
    more events from a 207 response are still failing. Only the events that
    keep failing are reported / re-buffered; events the endpoint accepted are
    never re-sent.

    Retryable 207 failures (e.g. transient BigQuery streaming errors) are
    re-sent with only the failing subset. Because ``telemetry.js`` passes
    each row's ``event_id`` as the BigQuery ``insertId``, any row that was
    already accepted within the streaming buffer (~1-minute window) is
    de-duplicated rather than written twice, so resending is safe.
    """


class NonRetryablePartialFailureError(PartialFailureError):
    """HTTP 207 failure for events that will never succeed on retry.

    Raised for permanent validation failures (the endpoint reports these
    with an ``index`` field referencing the rejected event's position in the
    batch). These events are dropped rather than re-buffered, since
    re-sending the same payload would fail identically.
    """


# ---------------------------------------------------------------------------
# RpiTelemetrySender
# ---------------------------------------------------------------------------


class RpiTelemetrySender:
    """Send telemetry events to the Cloud Function ingestion endpoint.

    Parameters
    ----------
    endpoint:
        Full HTTPS URL of the ``telemetryIngestion`` Cloud Function. Falls
        back to the ``TELEMETRY_ENDPOINT`` environment variable. Raises
        ``ValueError`` at construction time if neither is set.
    api_key:
        API key sent in the ``X-API-Key`` request header. Falls back to the
        ``TELEMETRY_API_KEY`` environment variable (default ``""``).
    batch_size:
        Maximum number of events per HTTP request. Falls back to the
        ``TELEMETRY_BATCH_SIZE`` environment variable, then
        :data:`DEFAULT_BATCH_SIZE`.
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

    Attributes
    ----------
    flush_interval:
        Read from ``TELEMETRY_FLUSH_INTERVAL`` (default
        :data:`DEFAULT_FLUSH_INTERVAL_S`). Not used internally by this
        class — exposed for a future periodic-collection loop to read, the
        same way ``StatusCollector`` uses its own interval constants on the
        EV3 side.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        *,
        batch_size: Optional[int] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: int = DEFAULT_TIMEOUT_S,
        threaded: bool = False,
        on_success: Optional[Callable[[int], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        endpoint = endpoint if endpoint is not None else os.environ.get("TELEMETRY_ENDPOINT", "")
        if not endpoint:
            raise ValueError(
                "RpiTelemetrySender requires an endpoint - pass endpoint=... "
                "or set the TELEMETRY_ENDPOINT environment variable."
            )

        if batch_size is None:
            batch_size = int(os.environ.get("TELEMETRY_BATCH_SIZE", DEFAULT_BATCH_SIZE))
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")

        self.endpoint = endpoint
        self.api_key = api_key if api_key is not None else os.environ.get("TELEMETRY_API_KEY", "")
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.timeout = timeout
        self.threaded = threaded
        self.on_success = on_success
        self.on_error = on_error
        self.flush_interval = float(
            os.environ.get("TELEMETRY_FLUSH_INTERVAL", DEFAULT_FLUSH_INTERVAL_S)
        )
        # Per-event error detail from the most recent 207 response, keyed by
        # event_id - used only to enrich the final give-up log message with
        # *why* the endpoint is rejecting events, not just how many.
        self._last_207_errors: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------
    # Public send interface
    # ------------------------------------------------------------------

    def send_events(self, events: List[Dict[str, Any]]) -> bool:
        """Send *events* to the ingestion endpoint, batching as needed.

        Returns ``True`` if all chunks were sent successfully; ``False`` if
        any chunk ultimately failed after all retries.
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

        Returns immediately. Use :attr:`on_success` / :attr:`on_error`
        callbacks to observe the result.
        """
        if not events:
            return
        t = threading.Thread(
            target=self._async_worker,
            args=(list(events), collector),
            daemon=True,
        )
        t.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _batches(self, events: List[Dict[str, Any]]):
        """Yield successive slices of *events* of length :attr:`batch_size`."""
        for i in range(0, len(events), self.batch_size):
            yield events[i: i + self.batch_size]

    def _send_batch_with_retry(self, batch: List[Dict[str, Any]]):
        """Send *batch* with retries, returning ``(fully_ok, unsent_events)``.

        On an HTTP 207 the response body is parsed per-event: validation
        failures (which carry an ``index``) are dropped as permanent, while
        transient BigQuery failures (which carry an ``event_id``) are resent
        with only the failing subset.
        """
        current = list(batch)
        wait = DEFAULT_RETRY_BASE_S
        had_permanent = False

        for attempt in range(self.max_retries + 1):
            try:
                accepted, permanent, retryable = self._post_batch(current)
            except Exception as exc:  # noqa: BLE001 - network / non-2xx HTTP
                if attempt < self.max_retries:
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
                        "telemetry endpoint permanently rejected "
                        "{} event(s) (validation failure, not retried)".format(len(permanent))
                    )
                )

            if not retryable:
                return (not had_permanent), []

            if attempt < self.max_retries:
                current = retryable
                _time.sleep(wait)
                wait *= 2
                continue

            self._fire_error(
                PartialFailureError(
                    "HTTP 207 partial failure: {} event(s) still failing after {} retries. "
                    "Sample errors: {}".format(
                        len(retryable), self.max_retries, self._sample_207_errors(retryable)
                    )
                )
            )
            return False, list(retryable)

        return False, list(current)

    def _send_events_with_unsent(self, events: List[Dict[str, Any]]):
        """Send *events* in batches, returning ``(all_ok, unsent_events)``."""
        if not events:
            return True, []

        all_ok = True
        unsent = []
        batch_start = 0
        total = len(events)

        while batch_start < total:
            batch = events[batch_start: batch_start + self.batch_size]
            fully_ok, batch_unsent = self._send_batch_with_retry(batch)
            if not fully_ok:
                all_ok = False
            unsent.extend(batch_unsent)

            # Whole batch unsent -> likely a transient/endpoint-wide failure.
            # Stop sending and treat the remainder as unsent.
            if batch_unsent and len(batch_unsent) == len(batch):
                unsent.extend(events[batch_start + self.batch_size:])
                return False, unsent

            batch_start += self.batch_size

        return all_ok, unsent

    def _post_batch(self, batch: List[Dict[str, Any]]):
        """Execute a single HTTP POST for *batch*.

        Returns a ``(accepted, permanent, retryable)`` tuple of event lists.
        Raises ``OSError``/``URLError`` for transport errors or unexpected
        HTTP statuses so the caller applies transient-failure retry/back-off.
        """
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        body = json.dumps({"events": batch}).encode("utf-8")
        req = urllib_request.Request(self.endpoint, data=body, headers=headers, method="POST")

        try:
            with urllib_request.urlopen(req, timeout=self.timeout) as response:
                status = response.status
                body_text = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            status = exc.code
            try:
                body_text = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - reading the error body is best-effort
                body_text = ""

        status_int = int(status)

        if status_int == 207:
            return self._classify_207(batch, body_text)

        if 200 <= status_int < 300:
            return list(batch), [], []

        if status_int == 400:
            # Deterministic client/validation error - never retry.
            return [], list(batch), []

        raise OSError(
            "HTTP {} from telemetry endpoint: {}".format(status, body_text[:200])
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
            print("[RpiTelemetrySender] ERROR: {}".format(exc))

    def _classify_207(self, batch: List[Dict[str, Any]], response_text: str):
        """Split a 207 batch into ``(accepted, permanent, retryable)``.

        Validation failures carry an ``index`` (permanent); BigQuery
        streaming failures carry the ``event_id`` (retryable). Anything not
        reported as a failure was accepted.
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
        last_207_errors = {}
        for err in errors:
            if not isinstance(err, dict):
                continue
            idx = err.get("index")
            event_id = err.get("event_id")
            reasons = err.get("errors")
            key = event_id or (batch[idx].get("event_id") if isinstance(idx, int) and 0 <= idx < len(batch) else None)
            if key and reasons:
                last_207_errors[key] = reasons
            if isinstance(idx, int) and 0 <= idx < len(batch):
                permanent_indices.add(idx)
                continue
            if event_id:
                retryable_ids.add(event_id)
        self._last_207_errors = last_207_errors

        accepted = []
        permanent = []
        retryable = []
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

    def _sample_207_errors(self, events: List[Dict[str, Any]], limit: int = 3) -> str:
        """Return a short human-readable sample of the endpoint's per-event
        error reasons for *events*, using the detail captured by the most
        recent :meth:`_classify_207` call.
        """
        parts = []
        for event in events[:limit]:
            event_id = event.get("event_id")
            reasons = self._last_207_errors.get(event_id)
            if reasons:
                parts.append("{}: {}".format(event_id, "; ".join(str(r) for r in reasons)))
        if not parts:
            return "(no detail available)"
        remaining = len(events) - len(parts)
        sample = "; ".join(parts)
        if remaining > 0:
            sample += "; ... and {} more".format(remaining)
        return sample

    # ------------------------------------------------------------------
    # Convenience: flush collector and send
    # ------------------------------------------------------------------

    def flush_and_send(self, collector: Any, *, async_send: bool = False) -> Optional[bool]:
        """Flush *collector* and send all collected events.

        This drains both the on-disk overflow file (oldest events, persisted
        when the in-memory buffer overflowed) and the in-memory buffer,
        sending the overflow events first to preserve ordering.

        The overflow file is only ever cleared or rewritten *after* the send
        attempt completes (see :meth:`_reconcile_overflow`) — never deleted
        up front — so a crash or kill between loading and sending can never
        lose events that were sitting safely on disk.
        """
        overflow_events = self._drain_overflow(collector)
        events = overflow_events + collector.flush()
        if not events:
            return True
        if async_send:
            self.send_events_async(events, collector=collector)
            return None
        ok, unsent = self._send_events_with_unsent(events)
        if overflow_events:
            overflow_ids = {e.get("event_id") for e in overflow_events}
            still_unsent_overflow = [e for e in unsent if e.get("event_id") in overflow_ids]
            unsent = [e for e in unsent if e.get("event_id") not in overflow_ids]
            self._reconcile_overflow(collector, still_unsent_overflow)
        if unsent:
            self._restore_events_to_collector(collector, unsent)
        return ok

    def _drain_overflow(self, collector: Any) -> List[Dict[str, Any]]:
        """Load persisted overflow events without touching the file.

        The file is deliberately left untouched here — it is only cleared or
        rewritten once the send outcome is known, by
        :meth:`_reconcile_overflow`. Clearing it up front (the previous
        behavior) created a window where a crash between the clear and a
        confirmed successful send would lose the events permanently.
        """
        load = getattr(collector, "load_overflow", None)
        if not callable(load):
            return []
        try:
            events = load() or []
        except Exception:  # noqa: BLE001 - overflow drain must never crash a send
            return []
        return list(events)

    def _reconcile_overflow(
        self,
        collector: Any,
        still_unsent_overflow_events: List[Dict[str, Any]],
    ) -> None:
        """Rewrite the overflow file to contain only overflow-origin events
        that are still unsent after the send attempt.

        Called only after the send outcome is known, so the file is never
        cleared or rewritten based on an assumption of success. If every
        overflow-origin event was accepted, this clears the now-stale file;
        if some are still failing, it rewrites the file to hold exactly
        those, dropping only the ones confirmed sent.
        """
        clear = getattr(collector, "clear_overflow", None)
        if not callable(clear):
            return
        try:
            clear()
        except Exception:  # noqa: BLE001 - overflow bookkeeping must never crash a send
            return
        if not still_unsent_overflow_events:
            return
        persist = getattr(collector, "_persist_to_disk", None)
        if not callable(persist):
            return
        for event in still_unsent_overflow_events:
            try:
                persist(event)
            except Exception:  # noqa: BLE001
                pass

    def _restore_events_to_collector(
        self,
        collector: Any,
        events: List[Dict[str, Any]],
    ) -> None:
        """Best-effort restore of flushed events after failed send."""
        if not events:
            return
        buffer_event = getattr(collector, "_buffer_event", None)
        if callable(buffer_event):
            for event in events:
                buffer_event(event)
