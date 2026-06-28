"""
StatusCollector — periodic battery/motor telemetry and immediate device events.

Implements the requirements from PEN-124:

* Battery status is collected every **60 seconds** (configurable).
* Motor status is collected every **10 seconds** (configurable).
* Device connect/disconnect events are collected **immediately** via callbacks
  registered with :class:`~ev3_devices.DeviceManager`.
* Collection intervals are configurable via constructor arguments.

Usage::

    from telemetry.collector import TelemetryCollector
    from telemetry.status_collector import StatusCollector

    collector = TelemetryCollector(source="ev3")
    status = StatusCollector(collector, device_manager)
    status.start()

    # … robot runs …

    status.stop()
    events = collector.flush()
"""

from __future__ import annotations

import time
try:
    from typing import Any, Dict, Optional
except ImportError:  # pragma: no cover - MicroPython runtime path
    Any = Dict = Optional = None  # type: ignore[assignment,misc]

try:
    import threading as _threading
    _THREADING_AVAILABLE = True
except ImportError:
    _THREADING_AVAILABLE = False


# Default collection intervals (seconds)
DEFAULT_BATTERY_INTERVAL: int = 60
DEFAULT_MOTOR_INTERVAL: int = 10


class StatusCollector:
    """Collects battery, motor, and device-status telemetry from a DeviceManager.

    Parameters
    ----------
    collector:
        A :class:`~telemetry.collector.TelemetryCollector` to which events are
        written.
    device_manager:
        An :class:`~ev3_devices.DeviceManager` (or any object exposing
        ``get_battery_info()``, ``get_motor_status()``,
        ``register_disconnect_callback()``, and
        ``register_reconnect_callback()``).
    battery_interval:
        Seconds between ``battery_status`` events.  Defaults to
        :data:`DEFAULT_BATTERY_INTERVAL` (60).
    motor_interval:
        Seconds between ``motor_status`` events.  Defaults to
        :data:`DEFAULT_MOTOR_INTERVAL` (10).
    """

    def __init__(
        self,
        collector,
        device_manager,
        battery_interval: int = DEFAULT_BATTERY_INTERVAL,
        motor_interval: int = DEFAULT_MOTOR_INTERVAL,
    ) -> None:
        self.collector = collector
        self.device_manager = device_manager
        self.battery_interval = battery_interval
        self.motor_interval = motor_interval

        self._running: bool = False
        self._thread: Optional[Any] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start periodic collection and register device-change callbacks.

        Safe to call multiple times — subsequent calls are no-ops if already
        running.
        """
        if self._running:
            return

        self._register_device_callbacks()
        self._running = True

        if _THREADING_AVAILABLE:
            self._thread = _threading.Thread(
                target=self._run,
                daemon=True,
                name="StatusCollector",
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop periodic collection.

        Parameters
        ----------
        timeout:
            Seconds to wait for the background thread to finish.
        """
        self._running = False
        if self._thread is not None and _THREADING_AVAILABLE:
            self._thread.join(timeout=timeout)
            self._thread = None

    @property
    def is_running(self) -> bool:
        """``True`` while the periodic collection thread is active."""
        return self._running

    # ------------------------------------------------------------------
    # Manual / forced collection
    # ------------------------------------------------------------------

    def collect_battery_now(self) -> Optional[Dict[str, Any]]:
        """Collect a ``battery_status`` event immediately.

        Returns the event dict that was buffered, or ``None`` if battery data
        is unavailable.
        """
        return self._collect_battery_status()

    def collect_motor_now(self) -> Optional[Dict[str, Any]]:
        """Collect a ``motor_status`` event immediately.

        Returns the event dict that was buffered.
        """
        return self._collect_motor_status()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_device_callbacks(self) -> None:
        try:
            self.device_manager.register_disconnect_callback(
                self._on_device_disconnect
            )
            self.device_manager.register_reconnect_callback(
                self._on_device_reconnect
            )
        except Exception as exc:
            print("StatusCollector: device callback registration failed — "
                  "device connect/disconnect events will not be collected: {}".format(exc))

    def _run(self) -> None:
        """Main loop — runs in a daemon thread."""
        last_battery: float = 0.0
        last_motor: float = 0.0

        while self._running:
            now = time.time()

            if now - last_battery >= self.battery_interval:
                self._collect_battery_status()
                last_battery = now

            if now - last_motor >= self.motor_interval:
                self._collect_motor_status()
                last_motor = now

            time.sleep(1)

    def _collect_battery_status(self) -> Optional[Dict[str, Any]]:
        """Read battery info from DeviceManager and buffer a ``battery_status`` event."""
        try:
            info: Dict[str, Any] = self.device_manager.get_battery_info()
        except Exception:
            return None

        voltage_mv = info.get("voltage_mv")
        percentage = info.get("percentage")

        # Both required fields must be present and the battery must be readable.
        if voltage_mv is None or percentage is None or not info.get("available", True):
            return None

        return self.collector.collect(
            "battery_status",
            voltage_mv=voltage_mv,
            percentage=percentage,
            current_ma=info.get("current_ma"),
            battery_type=info.get("battery_type"),
        )

    def _collect_motor_status(self) -> Optional[Dict[str, Any]]:
        """Read motor status from DeviceManager and buffer a ``motor_status`` event."""
        try:
            motors: Dict[str, Any] = self.device_manager.get_motor_status()
        except Exception:
            return None

        return self.collector.collect("motor_status", motors=motors)

    def _on_device_disconnect(self, device_name: str, status_dict: Dict[str, Any]) -> None:
        """Called immediately when a device disconnects."""
        self.collector.collect(
            "device_status",
            device_name=device_name,
            status="disconnected",
            device_type=self._infer_device_type(device_name),
            port=status_dict.get("port"),
            previous_status="connected",
        )

    def _on_device_reconnect(self, device_name: str, status_dict: Dict[str, Any]) -> None:
        """Called immediately when a device reconnects."""
        self.collector.collect(
            "device_status",
            device_name=device_name,
            status="connected",
            device_type=self._infer_device_type(device_name),
            port=status_dict.get("port"),
            previous_status="disconnected",
        )

    @staticmethod
    def _infer_device_type(device_name: str) -> str:
        """Infer a ``device_type`` string from a device name."""
        name = device_name.lower()
        if "motor" in name:
            return "motor"
        if "sensor" in name or "ultrasonic" in name or "gyro" in name:
            return "sensor"
        if "controller" in name or "ps4" in name or "ps5" in name:
            return "controller"
        return "unknown"
