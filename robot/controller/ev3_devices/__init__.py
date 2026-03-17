"""
EV3 Devices Library

Device management and drive systems for LEGO MINDSTORMS EV3 robots.
Provides device initialization, safe operation, and various drive system implementations.
"""

from .device_manager import DeviceManager
from .drive_system import DriveSystem
from .tank_drive_system import TankDriveSystem
from .car_drive_system import CarDriveSystem
from .turret import Turret

__version__ = "1.0.0"
__all__ = [
    "DeviceManager",
    "DriveSystem", 
    "TankDriveSystem",
    "CarDriveSystem",
    "Turret"
]