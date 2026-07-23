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

HTTPS on Pybricks/EV3 MicroPython: curl subprocess, not ``urequests``
-----------------------------------------------------------------------
Pybricks EV3 MicroPython's bundled ``ussl``/``urequests`` cannot complete a
TLS handshake with Google Cloud Functions' frontend — every attempt fails
immediately with ``ssl_handshake_status: -256`` -> ``OSError: [Errno 5]
EIO``, not just intermittently (a known class of MicroPython issue: old
TLS ports choking on modern cert chains/handshake extensions, see
micropython/micropython#3647 and micropython/micropython-lib#374). EV3
MicroPython runs on top of ev3dev (real Debian Linux, not bare-metal
firmware), which ships a modern, properly maintained OpenSSL via ``curl`` —
so when the detected HTTP library is ``urequests``, :meth:`TelemetrySender.
_http_post` shells out to ``curl`` instead of calling ``urequests.post()``,
reusing the same ``os.popen()`` pattern ``ev3_devices.device_manager``
already relies on from this exact runtime. Falls back to ``urequests``
itself if ``curl`` isn't on ``PATH`` (e.g. a minimal image), so this can
never regress the previous (broken) behavior.

TODO(PEN-236): This is an interim fix, adequate for today's volume (30s
heartbeat interval; 120s-interval batched analytics flushes when
re-enabled) but not the most scalable transport long-term — no TLS session
reuse (fresh handshake every call), per-call process-spawn + temp-file
overhead. Revisit with a local relay daemon (persistent HTTP session,
Pybricks POSTs to it over loopback instead of spawning curl) once PEN-203's
5s heartbeat interval lands, analytics volume grows, or the EV3 fleet grows
enough for per-device curl overhead to matter.

Usage::

    from telemetry.sender import TelemetrySender

    sender = TelemetrySender(
        endpoint="https://europe-central2-wrack-control.cloudfunctions.net/unifiedIngress",
        device_id="ev3-001",
        device_token="your-per-device-token",
    )
    result = sender.send_events(events)   # list of event dicts
"""

import json
import os

# ``typing`` and ``from __future__ import annotations`` are unavailable on
# Pybricks/MicroPython.  Without the future import, function-signature
# annotations are evaluated at import time, so the fallback below provides a
# subscriptable stub (``Optional[str]`` etc. resolve to the stub harmlessly)
# that lets the module import on the EV3.
try:
    from typing import Any, Callable, Dict, List, Optional
except ImportError:  # pragma: no cover - MicroPython runtime path
    class _TypingStub:
        def __getitem__(self, item):
            return self

    Any = Callable = Dict = List = Optional = _TypingStub()  # type: ignore[assignment,misc]

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
# curl-subprocess HTTPS backend (works around Pybricks urequests' broken TLS)
# ---------------------------------------------------------------------------

# Cached across calls — checking ``PATH`` for ``curl`` on every send would be
# wasteful, and the answer never changes for the life of the process.
_CURL_AVAILABLE = None


def _curl_is_available() -> bool:
    """Return whether ``curl`` is on ``PATH``, cached after the first check."""
    global _CURL_AVAILABLE
    if _CURL_AVAILABLE is None:
        try:
            which = _run_shell_capture("command -v curl 2>/dev/null").strip()
            _CURL_AVAILABLE = bool(which)
        except Exception:  # noqa: BLE001 — treat any check failure as "unavailable"
            _CURL_AVAILABLE = False
    return _CURL_AVAILABLE


def _run_shell_capture(cmd: str) -> str:
    """Run *cmd* via the shell and return its captured stdout.

    Isolated as its own module-level function — rather than calling
    ``os.popen()`` directly inline — purely so tests can monkeypatch process
    execution without depending on ``curl`` actually being installed in CI,
    or touching a real shell at all.
    """
    return os.popen(cmd).read()  # noqa: S605 — no untrusted input reaches cmd


def _shell_quote(value: Any) -> str:
    """POSIX single-quote *value* for safe inclusion in a shell command line.

    MicroPython has no ``shlex.quote``. Wrapping in single quotes and
    escaping any embedded single quote as ``'"'"'`` is the standard POSIX
    trick: it closes the quoted string, emits a double-quoted single quote,
    then reopens the quoted string — safe for arbitrary bytes, including
    device tokens that might (in principle) contain shell metacharacters.
    """
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


class _CurlResponse:
    """Minimal duck-typed response returned by :meth:`TelemetrySender.
    _http_post_curl` — exposes just the ``status_code``/``text``/``close()``
    surface :meth:`TelemetrySender._post_batch` already expects from
    ``requests``/``urequests`` responses, so no other code needs to know a
    curl subprocess was involved instead of a Python HTTP client.
    """

    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def close(self) -> None:
        pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_S = 10
DEFAULT_RETRY_BASE_S = 1.0  # first retry wait; doubles each attempt
DEFAULT_CURL_TEMP_DIR = "/tmp"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PartialFailureError(OSError):
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
        Full HTTPS URL of the ``unifiedIngress`` Cloud Function (PEN-227).
    device_id:
        This device's identifier, sent in the ``X-Device-Id`` request header
        (also included in every event's ``device_id`` field).
    device_token:
        Per-device secret sent in the ``X-Device-Token`` request header.
        Generate/rotate with
        ``cloud/functions/setup-device-tokens.sh --device-id <device_id>``.
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
    curl_temp_dir:
        Directory used to stage the request body / response / stderr temp
        files when POSTing via the ``curl`` subprocess backend (see the
        module docstring's "HTTPS on Pybricks/EV3 MicroPython" section).
        Irrelevant when the detected HTTP library is ``requests`` or when
        ``curl`` isn't on ``PATH``. Defaults to ``/tmp``, matching
        :data:`telemetry.collector.DEFAULT_OVERFLOW_PATH`'s directory,
        already proven writable on-device by that overflow-persistence path.
    """

    def __init__(
        self,
        endpoint: str,
        device_id: str,
        device_token: str,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: int = DEFAULT_TIMEOUT_S,
        threaded: bool = False,
        on_success: Optional[Callable[[int], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        curl_temp_dir: str = DEFAULT_CURL_TEMP_DIR,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        self.endpoint = endpoint
        self.device_id = device_id
        self.device_token = device_token
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.timeout = timeout
        self.threaded = threaded
        self.on_success = on_success
        self.on_error = on_error
        self.curl_temp_dir = curl_temp_dir
        # Per-event error detail from the most recent 207 response, keyed by
        # event_id — used only to enrich the final give-up log message with
        # *why* the endpoint is rejecting events, not just how many.  Not
        # annotated (``self.x: Type = value``): MicroPython's parser only
        # supports PEP 526 annotations on simple names, not attribute
        # targets — annotating this raises SyntaxError at compile time.
        self._last_207_errors = {}
        # Combined with ``id(self)`` to build unique-enough curl temp file
        # names (see ``_http_post_curl``) — two sends from the *same*
        # instance never overlap in practice (one send at a time per
        # sender), but this still guards against it cheaply.
        self._curl_call_count = 0

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
        overflow_events: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Send *events* in a background daemon thread (fire-and-forget).

        Returns immediately.  Use :attr:`on_success` / :attr:`on_error`
        callbacks to observe the result.

        When ``threading`` is unavailable (some MicroPython builds) the send
        runs synchronously so events are never silently dropped.

        Parameters
        ----------
        overflow_events:
            The subset of *events* that originated from the on-disk overflow
            file (see :meth:`flush_and_send`). When provided, the background
            worker reconciles the overflow file once the send outcome is
            known — the same PEN-221 guarantee the synchronous path makes —
            instead of leaving the file untouched (and re-sent) forever.
        """
        if not events:
            return
        if not _HAS_THREADING:
            # No threads on this runtime — fall back to a blocking send rather
            # than dropping the events.
            self._async_worker(list(events), collector, overflow_events)
            return
        # Pybricks MicroPython's Thread() accepts only ``target``/``args`` —
        # passing ``daemon`` raises TypeError (PEN-188).
        t = _threading.Thread(
            target=self._async_worker,
            args=(list(events), collector, overflow_events),
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
    ):
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
                        "telemetry endpoint permanently rejected "
                        "{} event(s) (validation failure, not retried)".format(len(permanent))
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
                    "HTTP 207 partial failure: {} event(s) still failing after {} retries. "
                    "Sample errors: {}".format(
                        len(retryable), self.max_retries, self._sample_207_errors(retryable)
                    )
                )
            )
            return False, list(retryable)

        return False, list(current)

    def _send_events_with_unsent(
        self,
        events: List[Dict[str, Any]],
    ):
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
        unsent = []
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
    ):
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
        OSError
            Any non-2xx, non-207, non-400 HTTP status.
        Exception
            Transport errors from the underlying HTTP library.
        """
        headers = {
            "Content-Type": "application/json",
            "X-Device-Id": self.device_id,
            "X-Device-Token": self.device_token,
        }
        body = json.dumps({"events": batch})

        response = self._http_post(body, headers)

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

        raise OSError(
            "HTTP {} from telemetry endpoint: {}".format(status, str(body_text)[:200])
        )

    def _http_post(self, body: str, headers: Dict[str, str]):
        """POST *body* to :attr:`endpoint`.

        On Pybricks/EV3 MicroPython (``_HTTP_LIB == "urequests"``), routes
        through the ``curl`` subprocess backend instead of ``urequests.
        post()`` — see the module docstring's "HTTPS on Pybricks/EV3
        MicroPython" section for why ``urequests``' own TLS can't be used
        here at all. Falls back to ``urequests`` itself if ``curl`` isn't on
        ``PATH``, so a device/image without ``curl`` sees exactly today's
        (broken) behavior rather than a new failure mode.

        Otherwise (``requests`` on CPython/desktop/Raspberry Pi), tolerant of
        HTTP libraries that don't accept a ``timeout`` kwarg: Pybricks
        MicroPython's bundled ``urequests`` — unlike CPython's ``requests``
        — does not accept ``timeout`` on ``post()``; passing it raises
        ``TypeError: unexpected keyword argument 'timeout'`` (the same
        "unsupported kwarg" shape as the ``Thread(daemon=...)`` issue,
        PEN-188). Try with ``timeout`` first — needed so ``requests`` doesn't
        hang forever — and fall back without it.
        """
        if _HTTP_LIB == "urequests" and _curl_is_available():
            return self._http_post_curl(body, headers, self.timeout)

        try:
            return _http.post(  # type: ignore[union-attr]
                self.endpoint, data=body, headers=headers, timeout=self.timeout
            )
        except TypeError:
            return _http.post(  # type: ignore[union-attr]
                self.endpoint, data=body, headers=headers
            )

    def _http_post_curl(self, body: str, headers: Dict[str, str], timeout: int):
        """POST *body* via a ``curl`` subprocess rather than ``urequests``.

        TODO(PEN-236): interim fix — a per-call ``curl`` subprocess spawn
        with no TLS session reuse doesn't scale to a shorter heartbeat
        interval (PEN-203's 5s target) or restored high-volume analytics.
        Replace with a local relay daemon (persistent HTTP session on the
        ev3dev Debian layer; this class POSTs to it over loopback instead
        of spawning curl) if/when that volume actually shows up.

        Works around a hard TLS-handshake incompatibility between Pybricks
        EV3 MicroPython's bundled ``ussl``/``urequests`` and Google Cloud
        Functions' frontend (``ssl_handshake_status: -256`` ->
        ``OSError: [Errno 5] EIO``, reproducible on the very first request,
        every time — not a transient network issue). EV3 MicroPython runs on
        top of ev3dev (real Debian Linux), which ships a modern, properly
        maintained OpenSSL via ``curl``; ``ev3_devices.device_manager``
        already shells out successfully from this exact runtime
        (``os.popen("hostname -I")``), so this reuses that proven pattern
        rather than introducing a new capability to the runtime.

        The request body, response body, and curl's stderr are staged as
        temp files under :attr:`curl_temp_dir` (``curl --data-binary @file``
        avoids shell-escaping an arbitrary JSON payload; ``-o``/``2>``
        capture the response/error text without curl's own stdout — which
        is reserved for the ``-w '%{http_code}'`` status code, the one
        signal this method actually needs from the shell pipeline). All temp
        files are removed before returning, on every path, success or not.

        Returns a :class:`_CurlResponse`. Raises ``OSError`` if curl reports
        no valid HTTP response at all (exit status ``000`` — connection,
        TLS, or DNS failure at the curl level too), so the caller's existing
        transient-failure retry/back-off applies exactly as it would for a
        network exception from a Python HTTP client.
        """
        suffix = "{}_{}".format(id(self), self._curl_call_count)
        self._curl_call_count += 1
        body_path = "{}/wrack_telemetry_body_{}.json".format(self.curl_temp_dir, suffix)
        resp_path = "{}/wrack_telemetry_resp_{}.json".format(self.curl_temp_dir, suffix)
        err_path = "{}/wrack_telemetry_err_{}.log".format(self.curl_temp_dir, suffix)

        try:
            with open(body_path, "w") as fh:
                fh.write(body)
        except Exception as exc:  # noqa: BLE001 — surfaced as a normal send failure
            raise OSError("curl backend: failed to write request body: {}".format(exc))

        try:
            cmd_parts = ["curl", "-sS", "-X", "POST", _shell_quote(self.endpoint)]
            for key, value in headers.items():
                cmd_parts.append("-H")
                cmd_parts.append(_shell_quote("{}: {}".format(key, value)))
            cmd_parts.append("--data-binary")
            cmd_parts.append("@" + _shell_quote(body_path))
            cmd_parts.append("--max-time")
            cmd_parts.append(str(timeout))
            cmd_parts.append("-o")
            cmd_parts.append(_shell_quote(resp_path))
            cmd_parts.append("-w")
            cmd_parts.append("'%{http_code}'")
            cmd_parts.append("2>" + _shell_quote(err_path))

            status_text = _run_shell_capture(" ".join(cmd_parts)).strip()
        finally:
            self._curl_remove(body_path)

        status_code = int(status_text) if status_text.isdigit() else 0

        if status_code == 0:
            detail = self._curl_read_and_remove(err_path) or (
                "no HTTP response (connection/TLS/DNS failure)"
            )
            self._curl_remove(resp_path)
            raise OSError("curl POST failed: {}".format(detail))

        response_text = self._curl_read_and_remove(resp_path) or ""
        self._curl_remove(err_path)
        return _CurlResponse(status_code, response_text)

    @staticmethod
    def _curl_remove(path: str) -> None:
        """Best-effort delete of a curl temp file — must never raise."""
        try:
            os.remove(path)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _curl_read_and_remove(path: str) -> Optional[str]:
        """Read and delete a curl temp file, tolerating any failure."""
        text = None
        try:
            with open(path, "r") as fh:
                text = fh.read().strip()
        except Exception:  # noqa: BLE001
            text = None
        TelemetrySender._curl_remove(path)
        return text

    def _async_worker(
        self,
        events: List[Dict[str, Any]],
        collector: Optional[Any] = None,
        overflow_events: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Thread target for :meth:`send_events_async`.

        Mirrors the reconciliation the synchronous :meth:`flush_and_send`
        branch performs: overflow-origin events are split out of *unsent*
        and reconciled against the overflow file via
        :meth:`_split_and_reconcile_overflow` regardless of *ok*, so the file
        is cleared on success and rewritten (not left stale) on failure —
        this is the dominant, steady-state send path in production (the
        120s periodic flush in ``main.py``), so skipping reconciliation here
        would silently defeat PEN-221 for real-world usage.
        """
        ok, unsent = self._send_events_with_unsent(events)
        if collector is not None:
            unsent = self._split_and_reconcile_overflow(
                collector, overflow_events or [], unsent
            )
            if unsent:
                self._restore_events_to_collector(collector, unsent)

    def _fire_error(self, exc: Exception) -> None:
        """Invoke the ``on_error`` callback, or log if none is registered."""
        if self.on_error:
            self.on_error(exc)
        else:
            print("[TelemetrySender] ERROR: {}".format(exc))

    def _classify_207(
        self, batch: List[Dict[str, Any]], response_text: str
    ):
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
        # Keep the most recent detail for diagnostics — surfaced in the
        # give-up log message so operators can see *why*, not just how many.
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
        recent :meth:`_classify_207` call. Best-effort — falls back to a
        placeholder when no detail is available (e.g. an unparsable body).
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
            self.send_events_async(
                events, collector=collector, overflow_events=overflow_events
            )
            return None
        ok, unsent = self._send_events_with_unsent(events)
        unsent = self._split_and_reconcile_overflow(collector, overflow_events, unsent)
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
        Returns ``[]`` if the collector has no overflow support.
        """
        load = getattr(collector, "load_overflow", None)
        if not callable(load):
            return []
        try:
            events = load() or []
        except Exception:  # noqa: BLE001 — overflow drain must never crash a send
            return []
        return list(events)

    def _split_and_reconcile_overflow(
        self,
        collector: Any,
        overflow_events: List[Dict[str, Any]],
        unsent: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Split *unsent* into overflow-origin and buffer-origin subsets,
        reconcile the overflow file for the former via
        :meth:`_reconcile_overflow`, and return the latter for the caller
        to restore to the in-memory buffer.

        Shared by both the synchronous ``flush_and_send`` branch and
        :meth:`_async_worker` so the overflow file is reconciled identically
        regardless of which path a given send took (PEN-221 follow-up: the
        async path — the one actually used in steady-state production —
        used to skip this entirely). A no-op that returns *unsent* unchanged
        when *overflow_events* is empty, so :meth:`_reconcile_overflow` never
        touches the file when nothing came from disk this round.
        """
        if not overflow_events:
            return unsent
        overflow_ids = {e.get("event_id") for e in overflow_events}
        still_unsent_overflow = [e for e in unsent if e.get("event_id") in overflow_ids]
        buffer_origin_unsent = [e for e in unsent if e.get("event_id") not in overflow_ids]
        self._reconcile_overflow(collector, overflow_events, still_unsent_overflow)
        return buffer_origin_unsent

    def _reconcile_overflow(
        self,
        collector: Any,
        overflow_events: List[Dict[str, Any]],
        still_unsent_overflow_events: List[Dict[str, Any]],
    ) -> None:
        """Remove exactly the overflow-origin events confirmed sent by this
        attempt from the overflow file, once the send outcome is known.

        Deliberately a *removal*, not the earlier clear-then-rewrite
        approach: this method can run an arbitrary amount of time (an
        entire blocking network send, on the async path) after *its own
        caller* loaded the ``overflow_events`` snapshot passed in here, and
        in that window the control loop can concurrently evict a new event
        into the same file via ``_persist_to_disk``. A clear-then-rewrite
        based on the stale snapshot would delete that new event outright —
        it was never part of this send attempt, so it wouldn't be in
        *still_unsent_overflow_events* either, and would vanish permanently
        (PEN-221 follow-up). Removing only the confirmed-sent IDs is safe
        because :meth:`TelemetryCollector.remove_overflow_events` re-reads
        the file's *current* contents under its own lock immediately before
        rewriting it, so anything appended concurrently -- or any event in
        *still_unsent_overflow_events*, which is simply never touched here
        -- survives untouched. If the removal call itself fails, the
        confirmed-sent events are left on disk rather than lost: at worst
        they're resent (and de-duplicated) on the next cycle, never dropped.
        """
        if not overflow_events:
            return
        still_unsent_ids = {e.get("event_id") for e in still_unsent_overflow_events}
        confirmed_sent_ids = {
            e.get("event_id")
            for e in overflow_events
            if e.get("event_id") not in still_unsent_ids
        }
        if not confirmed_sent_ids:
            return
        remove = getattr(collector, "remove_overflow_events", None)
        if not callable(remove):
            return
        try:
            remove(confirmed_sent_ids)
        except Exception:  # noqa: BLE001 — overflow bookkeeping must never crash a send
            pass

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
