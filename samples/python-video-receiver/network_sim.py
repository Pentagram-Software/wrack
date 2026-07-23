"""
Network condition simulator for WAN validation testing.

Uses Linux ``tc qdisc netem`` to inject latency, jitter, and packet loss on a
named network interface.  All public classes can be used without root for unit
testing because the actual ``tc`` subprocess calls are guarded and mockable.

Typical usage::

    sim = NetworkSimulator(interface="eth0")
    with sim.apply(WAN_PRESETS["typical_wan"]):
        # run receiver and collect metrics
        pass
    # tc rules removed on context-manager exit

Preset names
------------
``ideal_lan``      – No impairments (0 ms latency, 0% loss, unlimited BW).
``good_wan``       – 20 ms / 5 ms jitter / 0.1% loss / 10 Mbps.
``typical_wan``    – 50 ms / 15 ms jitter / 0.5% loss / 5 Mbps.
``poor_wan``       – 120 ms / 30 ms jitter / 2% loss / 2 Mbps.
``mobile_4g``      – 80 ms / 20 ms jitter / 1% loss / 3 Mbps.
``mobile_3g``      – 200 ms / 50 ms jitter / 3% loss / 1 Mbps.
"""

from __future__ import annotations

import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator, Optional


# ---------------------------------------------------------------------------
# Configuration data class
# ---------------------------------------------------------------------------


@dataclass
class NetworkSimConfig:
    """Parameters for a simulated network condition.

    Attributes:
        name:           Human-readable label used in reports.
        latency_ms:     One-way added latency in milliseconds.
        jitter_ms:      Latency variation (uniform distribution) in ms.
        loss_pct:       Packet-loss percentage (0–100).
        bandwidth_kbps: Bandwidth limit in kilobits/s.  0 = unlimited.
        description:    Free-text description for reports/docs.
    """

    name: str
    latency_ms: float
    jitter_ms: float
    loss_pct: float
    bandwidth_kbps: int
    description: str = ""

    def is_impaired(self) -> bool:
        """Return True when this config applies any impairment."""
        return self.latency_ms > 0 or self.jitter_ms > 0 or self.loss_pct > 0


# ---------------------------------------------------------------------------
# Built-in presets
# ---------------------------------------------------------------------------


WAN_PRESETS: dict[str, NetworkSimConfig] = {
    "ideal_lan": NetworkSimConfig(
        name="ideal_lan",
        latency_ms=0,
        jitter_ms=0,
        loss_pct=0.0,
        bandwidth_kbps=0,
        description="No impairments – baseline LAN conditions",
    ),
    "good_wan": NetworkSimConfig(
        name="good_wan",
        latency_ms=20,
        jitter_ms=5,
        loss_pct=0.1,
        bandwidth_kbps=10_000,
        description="Good home broadband / low-latency WAN",
    ),
    "typical_wan": NetworkSimConfig(
        name="typical_wan",
        latency_ms=50,
        jitter_ms=15,
        loss_pct=0.5,
        bandwidth_kbps=5_000,
        description="Typical residential broadband with light congestion",
    ),
    "poor_wan": NetworkSimConfig(
        name="poor_wan",
        latency_ms=120,
        jitter_ms=30,
        loss_pct=2.0,
        bandwidth_kbps=2_000,
        description="Poor WAN – high latency and moderate loss",
    ),
    "mobile_4g": NetworkSimConfig(
        name="mobile_4g",
        latency_ms=80,
        jitter_ms=20,
        loss_pct=1.0,
        bandwidth_kbps=3_000,
        description="Typical 4G/LTE mobile connection",
    ),
    "mobile_3g": NetworkSimConfig(
        name="mobile_3g",
        latency_ms=200,
        jitter_ms=50,
        loss_pct=3.0,
        bandwidth_kbps=1_000,
        description="Legacy 3G mobile – worst-case WAN scenario",
    ),
}


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


class NetworkSimulator:
    """Apply and remove ``tc netem`` rules on a network interface.

    Args:
        interface: Network interface name (e.g. ``"eth0"``, ``"wlan0"``).
        dry_run:   When True, print ``tc`` commands instead of executing them.
                   Useful for CI environments without root privileges.
        _runner:   Injectable callable for ``tc`` subprocess execution.
                   Signature: ``runner(cmd: list[str]) -> subprocess.CompletedProcess``.
                   Defaults to ``subprocess.run``.  Override in tests.
    """

    def __init__(
        self,
        interface: str,
        dry_run: bool = False,
        _runner=None,
    ) -> None:
        self.interface = interface
        self.dry_run = dry_run
        self._runner = _runner or self._default_runner
        self._active_config: Optional[NetworkSimConfig] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(self, config: NetworkSimConfig) -> None:
        """Install netem rules described by *config*.

        Raises:
            RuntimeError: If ``tc`` returns a non-zero exit code.
        """
        self._clear()
        self._add_qdisc(config)
        self._active_config = config

    def clear(self) -> None:
        """Remove all netem rules installed by this simulator."""
        self._clear()
        self._active_config = None

    @contextmanager
    def apply_context(
        self, config: NetworkSimConfig
    ) -> Generator[None, None, None]:
        """Context manager that applies *config* on enter and clears on exit."""
        self.apply(config)
        try:
            yield
        finally:
            self.clear()

    @property
    def active_config(self) -> Optional[NetworkSimConfig]:
        """Return the currently active NetworkSimConfig, or None."""
        return self._active_config

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_qdisc(self, config: NetworkSimConfig) -> None:
        """Build and run the ``tc qdisc add`` command."""
        netem_parts = ["netem"]

        if config.latency_ms > 0 or config.jitter_ms > 0:
            netem_parts += [
                "delay",
                f"{config.latency_ms}ms",
                f"{config.jitter_ms}ms",
                "distribution",
                "normal",
            ]

        if config.loss_pct > 0:
            netem_parts += ["loss", f"{config.loss_pct}%"]

        if config.bandwidth_kbps > 0:
            # tbf handles rate limiting; netem handles delay/loss
            # Build a two-qdisc chain: tbf parent handles rate, netem child handles impairments
            tbf_cmd = [
                "tc", "qdisc", "add", "dev", self.interface,
                "root", "handle", "1:",
                "tbf",
                "rate", f"{config.bandwidth_kbps}kbit",
                "burst", "32kbit",
                "latency", "400ms",
            ]
            netem_cmd = [
                "tc", "qdisc", "add", "dev", self.interface,
                "parent", "1:", "handle", "10:",
            ] + netem_parts
            self._run(tbf_cmd)
            self._run(netem_cmd)
        else:
            # No rate limit – single netem qdisc
            cmd = [
                "tc", "qdisc", "add", "dev", self.interface,
                "root", "handle", "1:",
            ] + netem_parts
            self._run(cmd)

    def _clear(self) -> None:
        """Delete root qdisc (silently ignores 'No such file' errors)."""
        cmd = ["tc", "qdisc", "del", "dev", self.interface, "root"]
        try:
            self._run(cmd)
        except RuntimeError:
            # Already absent – that is fine
            pass

    def _run(self, cmd: list) -> subprocess.CompletedProcess:
        if self.dry_run:
            print("[dry_run] " + " ".join(str(c) for c in cmd))
            return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")
        return self._runner(cmd)

    @staticmethod
    def _default_runner(cmd: list) -> subprocess.CompletedProcess:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"tc command failed (exit {result.returncode}): "
                f"{' '.join(str(c) for c in cmd)}\n"
                f"stderr: {result.stderr.strip()}"
            )
        return result


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------


def tc_available() -> bool:
    """Return True if the ``tc`` binary is present in PATH."""
    try:
        result = subprocess.run(
            ["which", "tc"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
