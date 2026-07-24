"""Unit tests for edge/monitoring/system_metrics_collector.py (PEN-192)."""

import os
import tempfile
import time
from unittest.mock import MagicMock

import pytest

from system_metrics_collector import (
    DEFAULT_COLLECTION_INTERVAL,
    SystemMetricsSender,
    compute_cpu_percent,
    read_cpu_stat_sample,
    read_cpu_temp_c,
    read_memory_percent,
)

# ---------------------------------------------------------------------------
# Fixture helpers — write a temp file with given contents, return its path.
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_file(tmp_path):
    def _write(name: str, contents: str) -> str:
        path = tmp_path / name
        path.write_text(contents)
        return str(path)

    return _write


# ---------------------------------------------------------------------------
# read_cpu_stat_sample / compute_cpu_percent
# ---------------------------------------------------------------------------


class TestReadCpuStatSample:
    def test_parses_valid_cpu_line(self, tmp_file):
        path = tmp_file(
            "stat",
            "cpu  100 10 50 800 5 0 0 0 0 0\n"
            "cpu0 100 10 50 800 5 0 0 0 0 0\n",
        )
        idle_time, total_time = read_cpu_stat_sample(path)
        # idle (800) + iowait (5) = 805; total = sum of all 10 fields = 965
        assert idle_time == 805
        assert total_time == 965

    def test_missing_file_returns_none(self):
        assert read_cpu_stat_sample("/nonexistent/proc/stat") is None

    def test_malformed_line_returns_none(self, tmp_file):
        path = tmp_file("stat", "cpu  not numbers here\n")
        assert read_cpu_stat_sample(path) is None

    def test_too_few_fields_returns_none(self, tmp_file):
        path = tmp_file("stat", "cpu  100 10\n")
        assert read_cpu_stat_sample(path) is None

    def test_missing_cpu_prefix_returns_none(self, tmp_file):
        path = tmp_file("stat", "intr 12345\n")
        assert read_cpu_stat_sample(path) is None

    def test_empty_file_returns_none(self, tmp_file):
        path = tmp_file("stat", "")
        assert read_cpu_stat_sample(path) is None


class TestComputeCpuPercent:
    def test_none_prev_sample_returns_none(self):
        assert compute_cpu_percent(None, (100, 200)) is None

    def test_none_curr_sample_returns_none(self):
        assert compute_cpu_percent((100, 200), None) is None

    def test_computes_percent_from_delta(self):
        # 100 jiffies elapsed total, 20 of them idle -> 80% busy.
        prev = (50, 500)
        curr = (70, 600)
        assert compute_cpu_percent(prev, curr) == pytest.approx(80.0)

    def test_fully_idle_gives_zero_percent(self):
        prev = (500, 500)
        curr = (600, 600)
        assert compute_cpu_percent(prev, curr) == pytest.approx(0.0)

    def test_fully_busy_gives_hundred_percent(self):
        prev = (500, 1000)
        curr = (500, 1100)
        assert compute_cpu_percent(prev, curr) == pytest.approx(100.0)

    def test_no_elapsed_total_returns_none(self):
        """Two samples with the same total_time (clock oddity, or taken
        back-to-back with zero elapsed jiffies) must not divide by zero."""
        sample = (100, 500)
        assert compute_cpu_percent(sample, sample) is None

    def test_result_clamped_to_0_100_range(self):
        # A pathological delta (e.g. counters wrapped) should still clamp.
        prev = (0, 1000)
        curr = (2000, 1100)  # delta_idle > delta_total
        result = compute_cpu_percent(prev, curr)
        assert 0.0 <= result <= 100.0


# ---------------------------------------------------------------------------
# read_memory_percent
# ---------------------------------------------------------------------------


class TestReadMemoryPercent:
    def test_computes_percent_from_memavailable(self, tmp_file):
        path = tmp_file(
            "meminfo",
            "MemTotal:        1000000 kB\n"
            "MemFree:          100000 kB\n"
            "MemAvailable:     400000 kB\n",
        )
        # 100 * (1 - 400000/1000000) = 60%
        assert read_memory_percent(path) == pytest.approx(60.0)

    def test_missing_file_returns_none(self):
        assert read_memory_percent("/nonexistent/proc/meminfo") is None

    def test_missing_memavailable_returns_none(self, tmp_file):
        path = tmp_file("meminfo", "MemTotal:        1000000 kB\n")
        assert read_memory_percent(path) is None

    def test_missing_memtotal_returns_none(self, tmp_file):
        path = tmp_file("meminfo", "MemAvailable:     400000 kB\n")
        assert read_memory_percent(path) is None

    def test_zero_memtotal_returns_none(self, tmp_file):
        path = tmp_file(
            "meminfo", "MemTotal:        0 kB\nMemAvailable:     0 kB\n"
        )
        assert read_memory_percent(path) is None

    def test_malformed_value_returns_none(self, tmp_file):
        path = tmp_file(
            "meminfo", "MemTotal:        not-a-number kB\nMemAvailable: 1 kB\n"
        )
        assert read_memory_percent(path) is None

    def test_fully_available_gives_zero_percent(self, tmp_file):
        path = tmp_file(
            "meminfo", "MemTotal:        1000 kB\nMemAvailable:    1000 kB\n"
        )
        assert read_memory_percent(path) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# read_cpu_temp_c
# ---------------------------------------------------------------------------


class TestReadCpuTempC:
    def test_parses_millidegrees(self, tmp_file):
        path = tmp_file("temp", "48213\n")
        assert read_cpu_temp_c(path) == pytest.approx(48.213)

    def test_missing_file_returns_none(self):
        assert read_cpu_temp_c("/nonexistent/thermal_zone0/temp") is None

    def test_malformed_content_returns_none(self, tmp_file):
        path = tmp_file("temp", "not-a-number\n")
        assert read_cpu_temp_c(path) is None

    def test_permission_error_returns_none(self, tmp_file, monkeypatch):
        path = tmp_file("temp", "48000\n")

        def _raise_permission_error(*args, **kwargs):
            raise PermissionError("Permission denied")

        monkeypatch.setattr("builtins.open", _raise_permission_error)
        assert read_cpu_temp_c(path) is None


# ---------------------------------------------------------------------------
# SystemMetricsSender
# ---------------------------------------------------------------------------


class TestSystemMetricsSenderTick:
    def _sender(self, tmp_file, *, cpu_lines, mem_contents, temp_contents="45000\n"):
        """Build a SystemMetricsSender wired to temp-file-backed proc/sys
        paths, plus a mock RpiTelemetryCollector/RpiTelemetrySender pair.
        """
        stat_path = tmp_file("stat", cpu_lines[0])
        mem_path = tmp_file("meminfo", mem_contents)
        temp_path = tmp_file("temp", temp_contents) if temp_contents is not None else "/nonexistent/temp"

        collector = MagicMock()
        collector.create_event.side_effect = lambda event_type, payload: {
            "event_id": "11111111-1111-4111-8111-111111111111",
            "event_type": event_type,
            "source": "rpi",
            "timestamp": "2026-01-01T00:00:00Z",
            "device_id": "rpi-camera-01",
            "session_id": "session-1",
            "payload": payload,
        }
        sender = MagicMock()

        s = SystemMetricsSender(
            collector,
            sender,
            interval=DEFAULT_COLLECTION_INTERVAL,
            proc_stat_path=stat_path,
            meminfo_path=mem_path,
            thermal_zone_path=temp_path,
        )
        return s, stat_path, collector, sender

    def test_first_tick_has_no_delta_and_sends_nothing(self, tmp_file):
        s, _, collector, sender = self._sender(
            tmp_file,
            cpu_lines=["cpu  100 0 0 800 0 0 0 0 0 0\n"],
            mem_contents="MemTotal: 1000000 kB\nMemAvailable: 500000 kB\n",
        )
        result = s.send_now()
        assert result is None
        collector.create_event.assert_not_called()
        sender.send_events.assert_not_called()

    def test_second_tick_sends_full_payload(self, tmp_file):
        s, stat_path, collector, sender = self._sender(
            tmp_file,
            cpu_lines=["cpu  100 0 0 800 0 0 0 0 0 0\n"],
            mem_contents="MemTotal: 1000000 kB\nMemAvailable: 500000 kB\n",
        )
        s.send_now()  # bootstrap tick — establishes prev sample

        # Advance the CPU counters: total +100, idle +20 -> 80% busy.
        with open(stat_path, "w") as fh:
            fh.write("cpu  180 0 0 820 0 0 0 0 0 0\n")

        # Wait for the first tick's tracked send thread to clear before the
        # second tick — send_now() skips the tick entirely otherwise (single
        # in-flight guarantee).
        for _ in range(50):
            if s._send_thread is None:
                break
            time.sleep(0.01)

        event = s.send_now()
        assert event is not None
        payload = event["payload"]
        assert payload["cpu_percent"] == pytest.approx(80.0)
        assert payload["memory_percent"] == pytest.approx(50.0)
        assert payload["cpu_temp_c"] == pytest.approx(45.0)

        # Critical for correct routing: unifiedIngress (cloud/functions/
        # ingress.js) reads this literal top-level field and defaults to
        # "event" (BigQuery) when it's absent -- a regression here would
        # silently misroute every sample away from Grafana Cloud.
        assert event["type"] == "health"

        # The send is dispatched on a tracked background thread — wait for
        # it to actually run before asserting on the mock.
        for _ in range(50):
            if sender.send_events.called:
                break
            time.sleep(0.01)
        sender.send_events.assert_called_once_with([event])

    def test_missing_temp_omits_field_but_still_sends(self, tmp_file):
        s, stat_path, collector, sender = self._sender(
            tmp_file,
            cpu_lines=["cpu  100 0 0 800 0 0 0 0 0 0\n"],
            mem_contents="MemTotal: 1000000 kB\nMemAvailable: 500000 kB\n",
            temp_contents=None,
        )
        s.send_now()
        with open(stat_path, "w") as fh:
            fh.write("cpu  180 0 0 820 0 0 0 0 0 0\n")
        for _ in range(50):
            if s._send_thread is None:
                break
            time.sleep(0.01)

        event = s.send_now()
        assert event is not None
        assert "cpu_temp_c" not in event["payload"]
        assert "cpu_percent" in event["payload"]
        assert "memory_percent" in event["payload"]

    def test_missing_memory_skips_whole_tick(self, tmp_file):
        s, stat_path, collector, sender = self._sender(
            tmp_file,
            cpu_lines=["cpu  100 0 0 800 0 0 0 0 0 0\n"],
            mem_contents="garbage, no MemTotal or MemAvailable here\n",
        )
        s.send_now()
        with open(stat_path, "w") as fh:
            fh.write("cpu  180 0 0 820 0 0 0 0 0 0\n")

        event = s.send_now()
        assert event is None
        sender.send_events.assert_not_called()

    def test_skips_tick_while_send_in_flight(self, tmp_file):
        s, stat_path, collector, sender = self._sender(
            tmp_file,
            cpu_lines=["cpu  100 0 0 800 0 0 0 0 0 0\n"],
            mem_contents="MemTotal: 1000000 kB\nMemAvailable: 500000 kB\n",
        )
        s.send_now()
        with open(stat_path, "w") as fh:
            fh.write("cpu  180 0 0 820 0 0 0 0 0 0\n")

        # Simulate an in-flight send by directly setting the marker rather
        # than racing a real thread.
        s._send_thread = MagicMock()
        s._send_thread.is_alive.return_value = True

        result = s.send_now()
        assert result is None
        collector.create_event.assert_not_called()

    def test_invalid_interval_rejected(self):
        with pytest.raises(ValueError):
            SystemMetricsSender(MagicMock(), MagicMock(), interval=0)

    def test_collection_failure_never_raises(self, tmp_file, monkeypatch):
        s, stat_path, collector, sender = self._sender(
            tmp_file,
            cpu_lines=["cpu  100 0 0 800 0 0 0 0 0 0\n"],
            mem_contents="MemTotal: 1000000 kB\nMemAvailable: 500000 kB\n",
        )
        s.send_now()

        def _raise(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(s, "_collect_metrics", _raise)
        result = s.send_now()  # must not raise
        assert result is None


class TestSystemMetricsSenderLifecycle:
    def test_start_stop(self, tmp_file):
        stat_path = tmp_file("stat", "cpu  100 0 0 800 0 0 0 0 0 0\n")
        mem_path = tmp_file("meminfo", "MemTotal: 1000000 kB\nMemAvailable: 500000 kB\n")
        temp_path = tmp_file("temp", "45000\n")
        s = SystemMetricsSender(
            MagicMock(),
            MagicMock(),
            interval=1,
            proc_stat_path=stat_path,
            meminfo_path=mem_path,
            thermal_zone_path=temp_path,
        )
        s.start()
        assert s.is_running is True
        s.stop(timeout=2.0)
        assert s.is_running is False

    def test_start_is_idempotent(self, tmp_file):
        stat_path = tmp_file("stat", "cpu  100 0 0 800 0 0 0 0 0 0\n")
        mem_path = tmp_file("meminfo", "MemTotal: 1000000 kB\nMemAvailable: 500000 kB\n")
        temp_path = tmp_file("temp", "45000\n")
        s = SystemMetricsSender(
            MagicMock(),
            MagicMock(),
            interval=1,
            proc_stat_path=stat_path,
            meminfo_path=mem_path,
            thermal_zone_path=temp_path,
        )
        s.start()
        first_thread = s._thread
        s.start()  # no-op
        assert s._thread is first_thread
        s.stop(timeout=2.0)
