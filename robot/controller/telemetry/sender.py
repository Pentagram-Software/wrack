"""
TelemetrySender — HTTP delivery of buffered events to the Cloud Function.

Sends batches of events to the ``telemetryIngestion`` Cloud Function endpoint
with API-key authentication, exponential-backoff retries, and optional
background (non-blocking) delivery.

Usage::

    from telemetry.sender import TelemetrySender
    from telemetry.collector import TelemetryCollector

    sender = TelemetrySender(
        endpoint="https://<region>-<project>.cloudfunctions.net/telemetryIngestion",
        api_key="your-secret-api-key",
    )

    collector = TelemetryCollector()
    # … collect events …
    sender.send_from_collector(collector)       # non-blocking background send
    # or:
    sender.send(collector.flush())              # blocking synchronous send
"""

from __future__ import annotations

import json
import time
from typing import Dict, List, Optional

try:
    import threading as _threading
    _THREADING_AVAILABLE = True
except ImportError:
    _THREADING_AVAILABLE = False

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:  # pragma: no cover  (always available in test env)
    _REQUESTS_AVAILABLE = False


class SendError(Exception):
    """Raised when an event batch could not be delivered after all retries."""


class TelemetrySender:
    """Sends batched telemetry events to the Cloud Function ingestion endpoint.

    Parameters
    ----------
    endpoint:
        Full URL of the ``telemetryIngestion`` Cloud Function.
    api_key:
        API key sent in the ``X-API-Key`` HTTP header.
    max_batch_size:
        Maximum number of events per HTTP request.  Defaults to ``100``.
    max_retries:
        Number of delivery attempts per batch before giving up.  Defaults
        to ``3``.
    retry_base_delay:
        Initial back-off delay in seconds.  Doubles on each retry.  Defaults
        to ``2.0``.
    timeout:
        HTTP request timeout in seconds.  Defaults to ``10``.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        max_batch_size: int = 100,
        max_retries: int = 3,
        retry_base_delay: float = 2.0,
        timeout: float = 10.0,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.max_batch_size = max_batch_size
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(self, events: List[Dict]) -> None:
        """Synchronously send *events* to the ingestion endpoint.

        Large lists are automatically split into batches no larger than
        ``max_batch_size``.

        Raises
        ------
        SendError
            If a batch cannot be delivered after all retry attempts.
        RuntimeError
            If the ``requests`` library is not available.
        """
        if not _REQUESTS_AVAILABLE:
            raise RuntimeError(
                "The 'requests' library is required for TelemetrySender. "
                "Install it with: pip install requests"
            )

        if not events:
            return

        for batch in self._chunks(events, self.max_batch_size):
            self._send_batch_with_retry(batch)

    def send_from_collector(self, collector) -> Optional[_threading.Thread] if _THREADING_AVAILABLE else None:  # type: ignore[return]
        """Flush *collector* and send events in a background daemon thread.

        Returns the :class:`threading.Thread` (or ``None`` when threading is
        unavailable, in which case events are sent synchronously).
        """
        events = collector.flush()
        if not events:
            return None

        if _THREADING_AVAILABLE:
            thread = _threading.Thread(
                target=self._send_ignoring_errors,
                args=(events,),
                daemon=True,
            )
            thread.start()
            return thread
        else:
            self._send_ignoring_errors(events)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send_batch_with_retry(self, batch: List[Dict]) -> None:
        delay = self.retry_base_delay
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self._post_batch(batch)
                return
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= 2

        raise SendError(
            f"Failed to deliver {len(batch)} event(s) after "
            f"{self.max_retries} attempt(s): {last_exc}"
        ) from last_exc

    def _post_batch(self, batch: List[Dict]) -> None:
        """POST a single batch to the endpoint; raises on non-2xx status."""
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        body = json.dumps({"events": batch})
        response = _requests.post(
            self.endpoint,
            data=body,
            headers=headers,
            timeout=self.timeout,
        )
        if not (200 <= response.status_code < 300):
            raise SendError(
                f"HTTP {response.status_code} from {self.endpoint}: "
                f"{response.text[:200]}"
            )

    def _send_ignoring_errors(self, events: List[Dict]) -> None:
        """Send events, suppressing all exceptions (for background use)."""
        try:
            self.send(events)
        except Exception:
            pass

    @staticmethod
    def _chunks(lst: list, size: int):
        """Yield successive *size*-length chunks of *lst*."""
        for i in range(0, len(lst), size):
            yield lst[i : i + size]
