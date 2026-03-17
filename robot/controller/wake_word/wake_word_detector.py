"""
Wake Word Detector using Mycroft Precise

This module provides wake word detection for the "Hey Wrack" phrase
using the Mycroft Precise engine. It follows the same event-driven
pattern as other controllers in the project.

Usage:
    detector = WakeWordDetector(model_path="hey_wrack.pb")
    detector.on_wake_word(lambda: print("Wake word detected!"))
    detector.start()
    # ... later ...
    detector.stop()
"""

import threading
import os
from event_handler import EventHandler

PRECISE_AVAILABLE = False
PreciseEngine = None
PreciseRunner = None
ReadWriteStream = None

try:
    from precise_runner import PreciseEngine, PreciseRunner, ReadWriteStream
    PRECISE_AVAILABLE = True
except ImportError:
    pass


DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "models",
    "hey_wrack.pb"
)

DEFAULT_ENGINE_PATH = "precise-engine"


class WakeWordDetector(EventHandler, threading.Thread):
    """
    Wake word detector that listens for the "Hey Wrack" phrase.
    
    Uses Mycroft Precise engine for lightweight, efficient wake word
    detection. Extends EventHandler to provide callback functionality
    and runs in a separate thread.
    
    Attributes:
        model_path (str): Path to the Precise model file (.pb)
        engine_path (str): Path to the precise-engine binary
        sensitivity (float): Detection sensitivity (0.0 to 1.0)
        trigger_level (int): Number of activations before triggering
        running (bool): Whether the detector is currently running
    """
    
    def __init__(self, model_path=None, engine_path=None, sensitivity=0.5,
                 trigger_level=3, speaker=None):
        """
        Initialize the wake word detector.
        
        Args:
            model_path (str, optional): Path to the wake word model file.
                Defaults to 'models/hey_wrack.pb' in the wake_word directory.
            engine_path (str, optional): Path to the precise-engine binary.
                Defaults to 'precise-engine' (expects it in PATH).
            sensitivity (float, optional): Detection sensitivity from 0.0 to 1.0.
                Higher values make detection more sensitive but may increase
                false positives. Default is 0.5.
            trigger_level (int, optional): Number of consecutive activations
                required before triggering the wake word event. Higher values
                reduce false positives. Default is 3.
            speaker (object, optional): EV3 speaker object for audio feedback.
        """
        EventHandler.__init__(self)
        threading.Thread.__init__(self, daemon=True)
        
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self.engine_path = engine_path or DEFAULT_ENGINE_PATH
        self.sensitivity = max(0.0, min(1.0, sensitivity))
        self.trigger_level = max(1, trigger_level)
        self.speaker = speaker
        
        self.running = False
        self.engine = None
        self.runner = None
        self._stop_event = threading.Event()
        self._detection_count = 0
        self._last_detection_time = 0
        
    def __str__(self):
        return "WakeWordDetector (Hey Wrack)"
    
    @staticmethod
    def is_available():
        """
        Check if Mycroft Precise is available on this system.
        
        Returns:
            bool: True if Precise engine and runner are importable.
        """
        return PRECISE_AVAILABLE
    
    def _on_activation(self):
        """
        Internal callback when the engine detects potential activation.
        
        This method handles the activation from Precise and triggers
        the wake_word event if the activation threshold is met.
        """
        import time
        current_time = time.time()
        
        if current_time - self._last_detection_time > 2.0:
            self._detection_count = 0
            
        self._detection_count += 1
        self._last_detection_time = current_time
        
        if self._detection_count >= self.trigger_level:
            self._detection_count = 0
            self._trigger_wake_word()
    
    def _trigger_wake_word(self):
        """Trigger the wake word detected event."""
        print("Wake word 'Hey Wrack' detected!")
        
        if self.speaker:
            try:
                self.speaker.beep(frequency=1000, duration=100)
            except Exception:
                pass
        
        self.trigger("wake_word")
    
    def run(self):
        """
        Main thread loop for wake word detection.
        
        This method runs in a separate thread and continuously listens
        for the wake word until stop() is called.
        """
        if not PRECISE_AVAILABLE:
            print("ERROR: Mycroft Precise is not installed.")
            print("Install with: pip install precise-runner precise-engine")
            return
        
        if not os.path.exists(self.model_path):
            print("ERROR: Wake word model not found at: {}".format(self.model_path))
            print("Please ensure the model file exists or train a custom model.")
            return
        
        try:
            print("Initializing wake word detector...")
            print("Model: {}".format(self.model_path))
            print("Sensitivity: {}".format(self.sensitivity))
            
            self.engine = PreciseEngine(
                self.engine_path,
                self.model_path,
                sensitivity=self.sensitivity
            )
            
            self.runner = PreciseRunner(
                self.engine,
                on_activation=self._on_activation,
                trigger_level=self.trigger_level
            )
            
            self.running = True
            self.runner.start()
            
            print("Wake word detector started - listening for 'Hey Wrack'...")
            
            if self.speaker:
                try:
                    self.speaker.beep(frequency=800, duration=100)
                except Exception:
                    pass
            
            self._stop_event.wait()
            
        except FileNotFoundError as e:
            print("ERROR: Precise engine binary not found: {}".format(e))
            print("Install with: pip install precise-engine")
        except Exception as e:
            print("ERROR: Failed to start wake word detector: {}".format(e))
        finally:
            self._cleanup()
    
    def _cleanup(self):
        """Clean up resources when stopping."""
        self.running = False
        
        if self.runner:
            try:
                self.runner.stop()
            except Exception:
                pass
            self.runner = None
            
        if self.engine:
            try:
                self.engine.stop()
            except Exception:
                pass
            self.engine = None
        
        print("Wake word detector stopped.")
    
    def stop(self):
        """
        Stop the wake word detector.
        
        This method signals the detector thread to stop and cleans up
        resources. Safe to call multiple times.
        """
        self._stop_event.set()
        self._cleanup()
    
    def is_running(self):
        """
        Check if the detector is currently running.
        
        Returns:
            bool: True if actively listening for wake words.
        """
        return self.running
    
    def on_wake_word(self, callback):
        """
        Register a callback for when the wake word is detected.
        
        Args:
            callback (callable): Function to call when "Hey Wrack" is detected.
                The callback receives the WakeWordDetector instance as argument.
        
        Example:
            detector.on_wake_word(lambda d: print("Hello!"))
        """
        self.on("wake_word", callback)
    
    def on_detection(self, callback):
        """
        Alias for on_wake_word for API consistency.
        
        Args:
            callback (callable): Function to call when wake word is detected.
        """
        self.on_wake_word(callback)
    
    def get_status(self):
        """
        Get the current status of the wake word detector.
        
        Returns:
            dict: Status information including running state, model path,
                and configuration.
        """
        return {
            "running": self.running,
            "available": PRECISE_AVAILABLE,
            "model_path": self.model_path,
            "model_exists": os.path.exists(self.model_path),
            "sensitivity": self.sensitivity,
            "trigger_level": self.trigger_level
        }


class MockWakeWordDetector(EventHandler, threading.Thread):
    """
    Mock wake word detector for testing without Mycroft Precise.
    
    This class provides the same interface as WakeWordDetector but
    doesn't require the Precise engine. Useful for testing and
    development on systems without audio hardware.
    """
    
    def __init__(self, model_path=None, engine_path=None, sensitivity=0.5,
                 trigger_level=3, speaker=None):
        """Initialize mock detector with same interface as real detector."""
        EventHandler.__init__(self)
        threading.Thread.__init__(self, daemon=True)
        
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self.engine_path = engine_path or DEFAULT_ENGINE_PATH
        self.sensitivity = max(0.0, min(1.0, sensitivity))
        self.trigger_level = max(1, trigger_level)
        self.speaker = speaker
        
        self.running = False
        self._stop_event = threading.Event()
    
    def __str__(self):
        return "MockWakeWordDetector (Hey Wrack)"
    
    @staticmethod
    def is_available():
        """Mock is always available."""
        return True
    
    def run(self):
        """Run mock detector (just waits for stop signal)."""
        self.running = True
        print("Mock wake word detector started (no actual detection)")
        self._stop_event.wait()
        self.running = False
        print("Mock wake word detector stopped")
    
    def stop(self):
        """Stop the mock detector."""
        self._stop_event.set()
        self.running = False
    
    def is_running(self):
        """Check if mock is running."""
        return self.running
    
    def on_wake_word(self, callback):
        """Register wake word callback."""
        self.on("wake_word", callback)
    
    def on_detection(self, callback):
        """Alias for on_wake_word."""
        self.on_wake_word(callback)
    
    def simulate_detection(self):
        """
        Simulate a wake word detection for testing.
        
        Manually triggers the wake_word event as if the phrase
        was actually detected.
        """
        print("Simulating wake word detection...")
        if self.speaker:
            try:
                self.speaker.beep(frequency=1000, duration=100)
            except Exception:
                pass
        self.trigger("wake_word")
    
    def get_status(self):
        """Get mock detector status."""
        return {
            "running": self.running,
            "available": True,
            "model_path": self.model_path,
            "model_exists": False,
            "sensitivity": self.sensitivity,
            "trigger_level": self.trigger_level,
            "mock": True
        }
