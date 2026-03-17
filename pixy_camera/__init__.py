"""
Pixy Camera Library

Interface for Pixy2 camera on EV3 MicroPython.
Provides event-driven block detection and camera control.
"""

from .pixy2_camera import Pixy2Camera

__version__ = "1.0.0"
__all__ = ["Pixy2Camera"]