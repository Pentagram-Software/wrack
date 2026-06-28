"""Unit tests for network_sim module."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from network_sim import (
    NetworkSimConfig,
    NetworkSimulator,
    WAN_PRESETS,
    tc_available,
)


# ---------------------------------------------------------------------------
# NetworkSimConfig
# ---------------------------------------------------------------------------


class TestNetworkSimConfig:
    def test_is_impaired_true_when_latency_present(self):
        cfg = NetworkSimConfig(
            name="test", latency_ms=10, jitter_ms=0, loss_pct=0.0, bandwidth_kbps=0
        )
        assert cfg.is_impaired() is True

    def test_is_impaired_true_when_jitter_present(self):
        cfg = NetworkSimConfig(
            name="test", latency_ms=0, jitter_ms=5, loss_pct=0.0, bandwidth_kbps=0
        )
        assert cfg.is_impaired() is True

    def test_is_impaired_true_when_loss_present(self):
        cfg = NetworkSimConfig(
            name="test", latency_ms=0, jitter_ms=0, loss_pct=1.0, bandwidth_kbps=0
        )
        assert cfg.is_impaired() is True

    def test_is_impaired_false_ideal_lan(self):
        cfg = WAN_PRESETS["ideal_lan"]
        assert cfg.is_impaired() is False

    def test_ideal_lan_preset_has_zero_loss(self):
        assert WAN_PRESETS["ideal_lan"].loss_pct == 0.0

    def test_mobile_3g_has_highest_latency(self):
        latencies = {name: p.latency_ms for name, p in WAN_PRESETS.items()}
        assert latencies["mobile_3g"] == max(latencies.values())


# ---------------------------------------------------------------------------
# WAN_PRESETS
# ---------------------------------------------------------------------------


class TestWanPresets:
    EXPECTED_PRESETS = {
        "ideal_lan",
        "good_wan",
        "typical_wan",
        "poor_wan",
        "mobile_4g",
        "mobile_3g",
    }

    def test_all_expected_presets_exist(self):
        assert self.EXPECTED_PRESETS == set(WAN_PRESETS.keys())

    @pytest.mark.parametrize("name", list(WAN_PRESETS.keys()))
    def test_preset_latency_non_negative(self, name):
        assert WAN_PRESETS[name].latency_ms >= 0

    @pytest.mark.parametrize("name", list(WAN_PRESETS.keys()))
    def test_preset_loss_pct_in_range(self, name):
        assert 0.0 <= WAN_PRESETS[name].loss_pct <= 100.0

    @pytest.mark.parametrize("name", list(WAN_PRESETS.keys()))
    def test_preset_bandwidth_non_negative(self, name):
        assert WAN_PRESETS[name].bandwidth_kbps >= 0

    def test_preset_names_match_keys(self):
        for key, preset in WAN_PRESETS.items():
            assert preset.name == key


# ---------------------------------------------------------------------------
# NetworkSimulator (uses injectable _runner to avoid real tc calls)
# ---------------------------------------------------------------------------


def _make_mock_runner(return_code: int = 0):
    """Return a callable that records calls and returns a fake CompletedProcess."""

    calls_list = []

    def runner(cmd):
        calls_list.append(cmd)
        if return_code != 0:
            raise RuntimeError(f"tc failed: {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, returncode=return_code, stdout="", stderr="")

    runner.calls = calls_list
    return runner


class TestNetworkSimulator:
    def test_apply_calls_tc_add_no_bandwidth(self):
        """apply() with no bandwidth limit calls a single tc qdisc add."""
        runner = _make_mock_runner()
        sim = NetworkSimulator(interface="eth0", _runner=runner)
        cfg = NetworkSimConfig(
            name="test",
            latency_ms=50,
            jitter_ms=10,
            loss_pct=1.0,
            bandwidth_kbps=0,
        )
        sim.apply(cfg)
        add_calls = [c for c in runner.calls if "add" in c]
        assert len(add_calls) == 1
        cmd = add_calls[0]
        assert "netem" in cmd
        assert "delay" in cmd
        assert "50ms" in cmd
        assert "loss" in cmd
        assert "1.0%" in cmd

    def test_apply_calls_two_tc_commands_with_bandwidth(self):
        """apply() with bandwidth limit issues tbf + netem qdisc pair."""
        runner = _make_mock_runner()
        sim = NetworkSimulator(interface="eth0", _runner=runner)
        cfg = NetworkSimConfig(
            name="test",
            latency_ms=50,
            jitter_ms=10,
            loss_pct=0.5,
            bandwidth_kbps=5000,
        )
        sim.apply(cfg)
        add_calls = [c for c in runner.calls if "add" in c]
        assert len(add_calls) == 2, f"Expected 2 add calls, got: {runner.calls}"

    def test_clear_calls_tc_qdisc_del(self):
        """clear() issues a tc qdisc del command."""
        runner = _make_mock_runner()
        sim = NetworkSimulator(interface="eth0", _runner=runner)
        sim.clear()
        del_calls = [c for c in runner.calls if "del" in c]
        assert len(del_calls) == 1
        assert "eth0" in del_calls[0]

    def test_clear_silently_ignores_tc_del_failure(self):
        """clear() tolerates RuntimeError from tc del (already absent)."""
        call_count = {"n": 0}

        def failing_runner(cmd):
            call_count["n"] += 1
            if "del" in cmd:
                raise RuntimeError("Cannot delete qdisc: No such file or directory")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        sim = NetworkSimulator(interface="eth0", _runner=failing_runner)
        sim.clear()  # Should not raise

    def test_active_config_set_after_apply(self):
        """active_config reflects the applied config."""
        runner = _make_mock_runner()
        sim = NetworkSimulator(interface="eth0", _runner=runner)
        cfg = WAN_PRESETS["good_wan"]
        sim.apply(cfg)
        assert sim.active_config is cfg

    def test_active_config_none_after_clear(self):
        """active_config is None after clear()."""
        runner = _make_mock_runner()
        sim = NetworkSimulator(interface="eth0", _runner=runner)
        sim.apply(WAN_PRESETS["good_wan"])
        sim.clear()
        assert sim.active_config is None

    def test_apply_context_manager_clears_on_exit(self):
        """apply_context() clears rules even when body raises."""
        runner = _make_mock_runner()
        sim = NetworkSimulator(interface="eth0", _runner=runner)
        try:
            with sim.apply_context(WAN_PRESETS["typical_wan"]):
                raise ValueError("deliberate error")
        except ValueError:
            pass
        del_calls = [c for c in runner.calls if "del" in c]
        assert len(del_calls) >= 1

    def test_dry_run_prints_and_does_not_call_runner(self, capsys):
        """dry_run=True prints commands instead of executing them."""
        real_runner = MagicMock()
        sim = NetworkSimulator(interface="eth0", dry_run=True, _runner=real_runner)
        sim.apply(WAN_PRESETS["good_wan"])
        real_runner.assert_not_called()
        captured = capsys.readouterr()
        assert "[dry_run]" in captured.out

    def test_apply_uses_interface_name(self):
        """The correct interface name appears in tc commands."""
        runner = _make_mock_runner()
        sim = NetworkSimulator(interface="wlan0", _runner=runner)
        sim.apply(WAN_PRESETS["typical_wan"])
        for cmd in runner.calls:
            if "add" in cmd or "del" in cmd:
                assert "wlan0" in cmd

    def test_apply_without_impairment_omits_delay_loss(self):
        """ideal_lan preset produces a netem command without delay or loss."""
        runner = _make_mock_runner()
        sim = NetworkSimulator(interface="eth0", _runner=runner)
        sim.apply(WAN_PRESETS["ideal_lan"])
        add_calls = [c for c in runner.calls if "add" in c]
        assert len(add_calls) == 1
        # netem still present as qdisc type but delay/loss flags omitted
        cmd = add_calls[0]
        assert "netem" in cmd
        assert "delay" not in cmd
        assert "loss" not in cmd


# ---------------------------------------------------------------------------
# tc_available
# ---------------------------------------------------------------------------


class TestTcAvailable:
    def test_returns_bool(self):
        result = tc_available()
        assert isinstance(result, bool)

    def test_returns_false_when_which_fails(self, monkeypatch):
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess([], returncode=1, stdout="", stderr=""),
        )
        assert tc_available() is False

    def test_returns_true_when_which_succeeds(self, monkeypatch):
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess([], returncode=0, stdout="/sbin/tc\n", stderr=""),
        )
        assert tc_available() is True
