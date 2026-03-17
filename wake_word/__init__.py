"""
Wake Word Detection Module

This module provides wake word detection using Mycroft Precise engine.
It detects the "Hey Wrack" phrase and triggers callbacks when detected.

The detector is designed to run on hardware with audio input capability
(microphone). On the EV3 brick, this typically requires an external
device like a Raspberry Pi with a USB microphone.
"""

from .wake_word_detector import WakeWordDetector

__version__ = "1.0.0"
__all__ = ["WakeWordDetector"]
