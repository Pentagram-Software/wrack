"""
Raspberry Pi system metrics collector (PEN-192).

Periodically reads CPU usage %, memory usage %, and CPU temperature from the
Pi's own `/proc` and `/sys` filesystems and posts them to the unified
Cloud Function ingress (PEN-227) as a `system_metrics` event tagged
`type="health"`, so the health leg (PEN-228) routes it to Grafana Cloud.
This is the local collector that replaces Grafana Alloy for Pi OS-level
metrics — see `docs/monitoring/architecture.md` ("Status vs. plan") and
`edge/monitoring/alloy/config.alloy` (superseded, kept for reference).

Runs on standard CPython (Raspberry Pi OS), so none of the MicroPython
compatibility guards used by the EV3 module (`robot/controller/telemetry/`)
are needed here — same rationale as `edge/vision/telemetry/`.

Sending is delegated to the shared Raspberry Pi telemetry module
(`edge/vision/telemetry/`, PEN-166) via `RpiTelemetryCollector` +
`RpiTelemetrySender`, reusing the same device identity
(`RPI_DEVICE_ID`, default `rpi-camera-01`) the video streamer already
authenticates as — this collector runs on the same physical Pi.

Usage (as a long-running process, e.g. under the systemd service in
`edge/monitoring/systemd/wrack-system-metrics.service`)::

    python3 system_metrics_collector.py

Configuration is entirely via environment variables (see
`RpiTelemetryCollector`/`RpiTelemetrySender` for `RPI_DEVICE_ID`,
`TELEMETRY_ENDPOINT`, `TELEMETRY_DEVICE_TOKEN`), plus
`SYSTEM_METRICS_INTERVAL` (seconds between samples; default 30, matching
`HeartbeatSender`'s own placeholder default on the EV3 side).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Any, Dict, Optional, Tuple

# edge/ is the parent of monitoring/; edge/vision/ hosts the shared RPi
# telemetry module (PEN-166). Put both on sys.path so we can import
# `telemetry` and `pi_telemetry_env` the same way video-streamer does.
_EDGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VISION_ROOT = os.path.join(_EDGE_ROOT, "vision")
for _path in (_EDGE_ROOT, _VISION_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from pi_telemetry_env import ensure_telemetry_endpoint  # noqa: E402
from telemetry.collector import RpiTelemetryCollector  # noqa: E402
from telemetry.schemas import ValidationError, validate_event  # noqa: E402
from telemetry.sender import RpiTelemetrySender  # noqa: E402

LOGGER = logging.getLogger("edge.monitoring.system_metrics_collector")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROC_STAT_PATH = "/proc/stat"
MEMINFO_PATH = "/proc/meminfo"
THERMAL_ZONE_PATH = "/sys/class/thermal/thermal_zone0/temp"

# Placeholder default — no PRD freshness target is defined for Pi OS
# resource gauges specifically (unlike EV3 liveness, PEN-203's 5s/15s
# target). Matches HeartbeatSender's own DEFAULT_HEARTBEAT_INTERVAL.
DEFAULT_COLLECTION_INTERVAL = 30

# A stuck/slow send must not accumulate one worker thread per tick forever
# (same reasoning as HeartbeatSender, robot/controller/telemetry/heartbeat.py)
# — a lost sample here is explicitly low-stakes (docs/monitoring/
# architecture.md: "not tracked — no historical value for raw OS resource
# samples"), so retrying only prolongs how long a tracked send thread can
# block for zero benefit. The next tick, DEFAULT_COLLECTION_INTERVAL seconds
# away, is just as good as a slow/failed one.
DEFAULT_SEND_TIMEOUT_S = 5
DEFAULT_SEND_MAX_RETRIES = 0

_EVENT_TYPE = "system_metrics"

# unifiedIngress (cloud/functions/ingress.js) routes purely on this literal
# top-level "type" field on the JSON record -- defaulting to "event" (the
# BigQuery/analytics leg) when absent. edge/vision/telemetry's
# RpiTelemetryCollector.create_event() has no concept of this field (PEN-166
# predates PEN-227/PEN-228's health/event split), so it must be added here
# explicitly -- omitting it would silently misroute every sample to
# BigQuery instead of Grafana Cloud. Mirrors the `record_type` param
# robot/controller/telemetry/collector.py's create_event() already grew for
# the same reason on the EV3 side.
_RECORD_TYPE_FIELD = "type"
_RECORD_TYPE_HEALTH = "health"

# 0-based indexes into the numeric fields *after* the "cpu" label itself —
# i.e. fields[1:] = [user, nice, system, idle, iowait, irq, softirq, steal,
# guest, guest_nice]. Only the first four are guaranteed on every kernel;
# idle (3) and iowait (4) both count as "not busy" — iowait is time spent
# waiting on disk I/O, still idle CPU-wise. Anything beyond these (irq/
# softirq/steal/guest*) is included in total_time but not idle_time.
_CPU_STAT_IDLE_FIELD_INDEXES = (3, 4)  # idle, iowait


# ---------------------------------------------------------------------------
# CPU usage % (requires two samples with a time delta — see module docstring)
# ---------------------------------------------------------------------------


def _parse_cpu_stat_line(line: str) -> Optional[Tuple[int, int]]:
    """Parse a `/proc/stat` "cpu " summary line into `(idle_time, total_time)`
    jiffies. Returns ``None`` if the line is malformed.
    """
    fields = line.split()
    if not fields or fields[0] != "cpu":
        return None
    try:
        values = [int(f) for f in fields[1:]]
    except ValueError:
        return None
    if len(values) < 4:
        return None
    idle_time = sum(values[i] for i in _CPU_STAT_IDLE_FIELD_INDEXES if i < len(values))
    total_time = sum(values)
    return idle_time, total_time


def read_cpu_stat_sample(path: str = PROC_STAT_PATH) -> Optional[Tuple[int, int]]:
    """Read and parse the current `(idle_time, total_time)` jiffie counters
    from `/proc/stat`. Returns ``None`` on any read/parse failure — the
    caller treats this the same as "no sample yet" (see
    :func:`compute_cpu_percent`).
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            first_line = fh.readline()
    except OSError as exc:
        LOGGER.warning("system_metrics_collector: failed to read %s: %s", path, exc)
        return None
    return _parse_cpu_stat_line(first_line)


def compute_cpu_percent(
    prev_sample: Optional[Tuple[int, int]],
    curr_sample: Optional[Tuple[int, int]],
) -> Optional[float]:
    """Compute CPU usage % from two `(idle_time, total_time)` samples.

    Returns ``None`` if either sample is missing, or if ``total_time``
    didn't advance between samples (clock oddity, or the two samples were
    taken back-to-back with no elapsed jiffies) — never raises, and never
    divides by zero.
    """
    if prev_sample is None or curr_sample is None:
        return None
    prev_idle, prev_total = prev_sample
    curr_idle, curr_total = curr_sample
    delta_total = curr_total - prev_total
    delta_idle = curr_idle - prev_idle
    if delta_total <= 0:
        return None
    percent = 100.0 * (1.0 - (delta_idle / delta_total))
    return max(0.0, min(100.0, percent))


# ---------------------------------------------------------------------------
# Memory usage %
# ---------------------------------------------------------------------------


def read_memory_percent(path: str = MEMINFO_PATH) -> Optional[float]:
    """Read memory usage % from `/proc/meminfo` as
    ``100 * (1 - MemAvailable / MemTotal)`` — the same semantics as
    `node_memory_MemAvailable_bytes` / `node_memory_MemTotal_bytes` (the
    ticket's own reference metric), which accounts for reclaimable
    cache/buffers rather than the cruder `MemFree`-based calculation.

    Returns ``None`` on any read/parse failure or if `MemTotal` is zero.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        LOGGER.warning("system_metrics_collector: failed to read %s: %s", path, exc)
        return None

    values: Dict[str, int] = {}
    for line in lines:
        parts = line.split(":", 1)
        if len(parts) != 2:
            continue
        key = parts[0].strip()
        if key not in ("MemTotal", "MemAvailable"):
            continue
        # Values are "<kB integer> kB" — the unit suffix is always kB for
        # these two keys per the kernel's own meminfo formatting.
        digits = parts[1].strip().split()[0]
        try:
            values[key] = int(digits)
        except ValueError:
            return None

    mem_total = values.get("MemTotal")
    mem_available = values.get("MemAvailable")
    if not mem_total or mem_available is None:
        return None

    percent = 100.0 * (1.0 - (mem_available / mem_total))
    return max(0.0, min(100.0, percent))


# ---------------------------------------------------------------------------
# CPU temperature
# ---------------------------------------------------------------------------


def read_cpu_temp_c(path: str = THERMAL_ZONE_PATH) -> Optional[float]:
    """Read CPU temperature in Celsius from `/sys/class/thermal/thermal_zone0/temp`
    (millidegrees C as a bare integer).

    Returns ``None`` on any read/parse failure (missing file, permission
    error, different thermal-zone layout on another Pi model) — the caller
    omits the `cpu_temp_c` field for that tick rather than skipping the
    whole payload (mirrors `HeartbeatSender`'s battery-read-failure
    isolation pattern, PEN-234).
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
    except OSError as exc:
        LOGGER.warning("system_metrics_collector: failed to read %s: %s", path, exc)
        return None
    try:
        millidegrees = int(raw)
    except ValueError:
        LOGGER.warning("system_metrics_collector: unexpected content in %s: %r", path, raw)
        return None
    return millidegrees / 1000.0


# ---------------------------------------------------------------------------
# SystemMetricsSender
# ---------------------------------------------------------------------------


class SystemMetricsSender:
    """Periodically samples CPU/memory/temp and sends a `system_metrics`
    event tagged `type="health"` to the unified ingress.

    Structurally mirrors `robot/controller/telemetry/heartbeat.py`'s
    `HeartbeatSender` (PEN-229): a dedicated, non-buffering, no-retry sender,
    with sends run on a single tracked background thread so a slow/hung
    send can never accumulate more than one worker — but without any of the
    MicroPython-only workarounds `HeartbeatSender` needs (this runs on
    standard CPython).

    Parameters
    ----------
    collector:
        A :class:`~telemetry.collector.RpiTelemetryCollector`, used only to
        build well-formed event envelopes. Metrics are never buffered
        through the collector's normal analytics path — each tick is sent
        immediately, and a lost sample is explicitly low-stakes (PEN-192).
    sender:
        A :class:`~telemetry.sender.RpiTelemetrySender` used to POST each
        sample. Should be configured with :data:`DEFAULT_SEND_TIMEOUT_S` /
        :data:`DEFAULT_SEND_MAX_RETRIES` (see their module-level docstring)
        rather than the shared analytics sender's defaults.
    interval:
        Seconds between collection ticks. Defaults to
        :data:`DEFAULT_COLLECTION_INTERVAL`.
    proc_stat_path, meminfo_path, thermal_zone_path:
        Overridable for testing; default to the real `/proc`/`/sys` paths.
    """

    def __init__(
        self,
        collector: RpiTelemetryCollector,
        sender: RpiTelemetrySender,
        interval: int = DEFAULT_COLLECTION_INTERVAL,
        proc_stat_path: str = PROC_STAT_PATH,
        meminfo_path: str = MEMINFO_PATH,
        thermal_zone_path: str = THERMAL_ZONE_PATH,
    ) -> None:
        if interval <= 0:
            raise ValueError("interval must be a positive integer")
        self.collector = collector
        self.sender = sender
        self.interval = interval
        self.proc_stat_path = proc_stat_path
        self.meminfo_path = meminfo_path
        self.thermal_zone_path = thermal_zone_path

        # Carried across ticks (in-process state) rather than taken as two
        # blocking samples per tick — CPU% needs a time delta between two
        # /proc/stat reads, and reusing the previous tick's sample avoids
        # adding an extra blocking sleep to every collection cycle.
        self._prev_cpu_sample: Optional[Tuple[int, int]] = None

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Tracks the single in-flight send worker (None when idle) — see
        # HeartbeatSender's docstring for why this bound matters.
        self._send_thread: Optional[threading.Thread] = None
        self._send_lock = threading.Lock()
        self._send_generation = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the periodic collection loop. Safe to call multiple times."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the periodic collection loop, waiting briefly for any
        in-flight send.
        """
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        if self._send_thread is not None:
            self._send_thread.join(timeout=timeout)

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Manual / forced tick
    # ------------------------------------------------------------------

    def send_now(self) -> Optional[Dict[str, Any]]:
        """Collect and send a single tick immediately.

        Returns the event dict handed to the sender, or ``None`` if this
        tick had no usable CPU-usage delta yet (the very first tick after
        construction — there is no previous `/proc/stat` sample to diff
        against), or if a previous send is still in flight.
        """
        return self._tick()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main loop — ticks every second (like `HeartbeatSender._run`)
        rather than sleeping for the whole interval, so :meth:`stop` remains
        responsive instead of blocking for up to `interval` seconds.
        """
        last = -self.interval  # fire immediately on the first tick
        while self._running:
            now = time.time()
            if now - last >= self.interval:
                self._tick()
                last = now
            time.sleep(1)

    def _collect_metrics(self) -> Optional[Dict[str, Any]]:
        """Build one tick's payload, or ``None`` if no CPU-usage delta is
        available yet (bootstrap tick).

        A bad read of memory or temperature must never prevent CPU% (or vice
        versa) — each reader isolates its own failure; only `cpu_percent`
        being unavailable skips the whole tick, since it's the one field
        with no meaningful fallback (0% would misrepresent an unknown state,
        unlike temperature, which can simply be omitted).
        """
        curr_cpu_sample = read_cpu_stat_sample(self.proc_stat_path)
        cpu_percent = compute_cpu_percent(self._prev_cpu_sample, curr_cpu_sample)
        self._prev_cpu_sample = curr_cpu_sample

        if cpu_percent is None:
            return None

        memory_percent = read_memory_percent(self.meminfo_path)
        if memory_percent is None:
            LOGGER.warning("system_metrics_collector: memory_percent unavailable this tick — skipping")
            return None

        payload: Dict[str, Any] = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
        }

        cpu_temp_c = read_cpu_temp_c(self.thermal_zone_path)
        if cpu_temp_c is not None:
            payload["cpu_temp_c"] = cpu_temp_c

        return payload

    def _tick(self) -> Optional[Dict[str, Any]]:
        """Collect one sample and hand it to the send worker.

        Skips the tick entirely while a previous send is still in flight,
        rather than spawning another thread on top of it (mirrors
        `HeartbeatSender._send_heartbeat`). A bug collecting metrics, or a
        send failure, must never kill the background loop — it should just
        skip this tick.
        """
        if self._send_thread is not None:
            return None

        try:
            payload = self._collect_metrics()
        except Exception as exc:  # noqa: BLE001 — one bad collection must never kill the loop
            LOGGER.warning("system_metrics_collector: failed to collect metrics: %s", exc)
            return None

        if payload is None:
            return None

        event = self.collector.create_event(_EVENT_TYPE, payload)
        event[_RECORD_TYPE_FIELD] = _RECORD_TYPE_HEALTH
        try:
            validate_event(event)
        except ValidationError as exc:
            # Defensive: catches a schema/collector logic bug rather than
            # silently POSTing a malformed payload — should never trigger in
            # practice since _collect_metrics only ever produces
            # already-valid fields.
            LOGGER.warning("system_metrics_collector: built an invalid event, dropping tick: %s", exc)
            return None

        with self._send_lock:
            if self._send_thread is not None:
                return None

            self._send_generation += 1
            generation = self._send_generation
            self._send_thread = threading.Thread(
                target=self._send_worker, args=(event, generation), daemon=True
            )
            self._send_thread.start()

        return event

    def _send_worker(self, event: Dict[str, Any], generation: int) -> None:
        """Thread target: perform one blocking send, then clear the
        in-flight marker.
        """
        try:
            self.sender.send_events([event])
        except Exception as exc:  # noqa: BLE001 — one bad send must never kill the loop
            LOGGER.warning("system_metrics_collector: send failed: %s", exc)
        finally:
            with self._send_lock:
                if generation == self._send_generation:
                    self._send_thread = None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _interval_from_env() -> int:
    raw = os.environ.get("SYSTEM_METRICS_INTERVAL", str(DEFAULT_COLLECTION_INTERVAL))
    try:
        return int(raw)
    except ValueError:
        LOGGER.warning(
            "system_metrics_collector: invalid SYSTEM_METRICS_INTERVAL=%r, using default %ds",
            raw,
            DEFAULT_COLLECTION_INTERVAL,
        )
        return DEFAULT_COLLECTION_INTERVAL


def main() -> None:
    """Entry point for running this collector as a long-lived process
    (e.g. under the systemd service in
    `edge/monitoring/systemd/wrack-system-metrics.service`).

    All configuration is via environment variables — `RPI_DEVICE_ID`,
    `TELEMETRY_ENDPOINT`, `TELEMETRY_DEVICE_TOKEN` (read by
    `RpiTelemetryCollector`/`RpiTelemetrySender`), and
    `SYSTEM_METRICS_INTERVAL`.
    """
    logging.basicConfig(level=logging.INFO)

    # Load monitoring/system-metrics.env when TELEMETRY_ENDPOINT is unset
    # (written by make deploy-edge / write-pi-telemetry-env.sh). Raises a
    # clear error if the endpoint is still missing after that.
    ensure_telemetry_endpoint()

    # `validate` is irrelevant here: SystemMetricsSender never calls
    # collector.collect()/collect_raw() (which is what that flag gates) --
    # it builds each event via create_event() and validates it directly
    # (see _tick()), so the collector is used purely as an envelope factory.
    collector = RpiTelemetryCollector()
    sender = RpiTelemetrySender(
        timeout=DEFAULT_SEND_TIMEOUT_S,
        max_retries=DEFAULT_SEND_MAX_RETRIES,
    )
    metrics_sender = SystemMetricsSender(
        collector, sender, interval=_interval_from_env()
    )

    metrics_sender.start()
    LOGGER.info(
        "system_metrics_collector: started (device_id=%s, interval=%ds)",
        collector.device_id,
        metrics_sender.interval,
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        LOGGER.info("system_metrics_collector: stopping")
        metrics_sender.stop()


if __name__ == "__main__":
    main()
