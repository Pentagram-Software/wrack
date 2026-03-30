"""
EV3 Devices Library

Device management and drive systems for LEGO MINDSTORMS EV3 robots.
Provides device initialization, safe operation, and various drive system implementations.
Includes port monitoring for device disconnect/reconnect handling.
"""

from .device_manager import DeviceManager
from .drive_system import DriveSystem
from .tank_drive_system import TankDriveSystem
from .car_drive_system import CarDriveSystem
from .turret import Turret
from .port_monitor import PortMonitor, SafeDeviceProxy

__version__ = "1.0.0"
__all__ = [
    "DeviceManager",
    "DriveSystem", 
    "TankDriveSystem",
    "CarDriveSystem",
    "Turret",
    "PortMonitor",
    "SafeDeviceProxy"
]