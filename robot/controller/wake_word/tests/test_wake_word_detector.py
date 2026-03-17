#!/usr/bin/env python3
"""
Tests for Wake Word Detector module

These tests verify the WakeWordDetector class functionality including:
- Initialization and configuration
- Event handling and callbacks
- Mock detector for testing without hardware
- Status reporting
"""

import pytest
import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from wake_word.wake_word_detector import (
    WakeWordDetector,
    MockWakeWordDetector,
    PRECISE_AVAILABLE,
    DEFAULT_MODEL_PATH,
    DEFAULT_ENGINE_PATH
)


class TestWakeWordDetectorInit:
    """Tests for WakeWordDetector initialization"""
    
    def test_default_initialization(self):
        """Test detector initializes with default values"""
        detector = WakeWordDetector()
        
        assert detector.model_path == DEFAULT_MODEL_PATH
        assert detector.engine_path == DEFAULT_ENGINE_PATH
        assert detector.sensitivity == 0.5
        assert detector.trigger_level == 3
        assert detector.speaker is None
        assert detector.running is False
    
    def test_custom_initialization(self):
        """Test detector initializes with custom values"""
        detector = WakeWordDetector(
            model_path="/custom/model.pb",
            engine_path="/custom/engine",
            sensitivity=0.7,
            trigger_level=5
        )
        
        assert detector.model_path == "/custom/model.pb"
        assert detector.engine_path == "/custom/engine"
        assert detector.sensitivity == 0.7
        assert detector.trigger_level == 5
    
    def test_sensitivity_clamping_high(self):
        """Test sensitivity is clamped to maximum 1.0"""
        detector = WakeWordDetector(sensitivity=1.5)
        assert detector.sensitivity == 1.0
    
    def test_sensitivity_clamping_low(self):
        """Test sensitivity is clamped to minimum 0.0"""
        detector = WakeWordDetector(sensitivity=-0.5)
        assert detector.sensitivity == 0.0
    
    def test_trigger_level_minimum(self):
        """Test trigger_level is at least 1"""
        detector = WakeWordDetector(trigger_level=0)
        assert detector.trigger_level == 1
        
        detector2 = WakeWordDetector(trigger_level=-5)
        assert detector2.trigger_level == 1
    
    def test_str_representation(self):
        """Test string representation"""
        detector = WakeWordDetector()
        assert str(detector) == "WakeWordDetector (Hey Wrack)"


class TestWakeWordDetectorStatus:
    """Tests for WakeWordDetector status methods"""
    
    def test_is_available_returns_bool(self):
        """Test is_available returns boolean"""
        result = WakeWordDetector.is_available()
        assert isinstance(result, bool)
        assert result == PRECISE_AVAILABLE
    
    def test_is_running_initially_false(self):
        """Test is_running returns False before start"""
        detector = WakeWordDetector()
        assert detector.is_running() is False
    
    def test_get_status_structure(self):
        """Test get_status returns correct structure"""
        detector = WakeWordDetector()
        status = detector.get_status()
        
        assert "running" in status
        assert "available" in status
        assert "model_path" in status
        assert "model_exists" in status
        assert "sensitivity" in status
        assert "trigger_level" in status
        
        assert status["running"] is False
        assert status["available"] == PRECISE_AVAILABLE
        assert status["sensitivity"] == 0.5
        assert status["trigger_level"] == 3


class TestWakeWordDetectorCallbacks:
    """Tests for WakeWordDetector callback functionality"""
    
    def test_on_wake_word_registers_callback(self):
        """Test on_wake_word registers callback correctly"""
        detector = WakeWordDetector()
        callback_called = []
        
        def my_callback(d):
            callback_called.append(True)
        
        detector.on_wake_word(my_callback)
        
        assert "wake_word" in detector.callbacks
        assert len(detector.callbacks["wake_word"]) == 1
    
    def test_on_detection_alias(self):
        """Test on_detection is alias for on_wake_word"""
        detector = WakeWordDetector()
        callback_called = []
        
        def my_callback(d):
            callback_called.append(True)
        
        detector.on_detection(my_callback)
        
        assert "wake_word" in detector.callbacks
        assert len(detector.callbacks["wake_word"]) == 1
    
    def test_multiple_callbacks(self):
        """Test multiple callbacks can be registered"""
        detector = WakeWordDetector()
        results = []
        
        detector.on_wake_word(lambda d: results.append(1))
        detector.on_wake_word(lambda d: results.append(2))
        detector.on_wake_word(lambda d: results.append(3))
        
        assert len(detector.callbacks["wake_word"]) == 3
    
    def test_trigger_calls_all_callbacks(self):
        """Test triggering wake_word calls all registered callbacks"""
        detector = WakeWordDetector()
        results = []
        
        detector.on_wake_word(lambda d: results.append("first"))
        detector.on_wake_word(lambda d: results.append("second"))
        
        detector.trigger("wake_word")
        
        assert "first" in results
        assert "second" in results


class TestMockWakeWordDetector:
    """Tests for MockWakeWordDetector"""
    
    def test_mock_initialization(self):
        """Test mock detector initializes correctly"""
        mock = MockWakeWordDetector()
        
        assert mock.model_path == DEFAULT_MODEL_PATH
        assert mock.sensitivity == 0.5
        assert mock.trigger_level == 3
        assert mock.running is False
    
    def test_mock_is_available_always_true(self):
        """Test mock is always available"""
        assert MockWakeWordDetector.is_available() is True
    
    def test_mock_str_representation(self):
        """Test mock string representation"""
        mock = MockWakeWordDetector()
        assert str(mock) == "MockWakeWordDetector (Hey Wrack)"
    
    def test_mock_get_status_includes_mock_flag(self):
        """Test mock status includes mock flag"""
        mock = MockWakeWordDetector()
        status = mock.get_status()
        
        assert "mock" in status
        assert status["mock"] is True
    
    def test_mock_simulate_detection_triggers_callback(self):
        """Test simulate_detection triggers wake_word callbacks"""
        mock = MockWakeWordDetector()
        results = []
        
        mock.on_wake_word(lambda d: results.append("detected"))
        mock.simulate_detection()
        
        assert "detected" in results
    
    def test_mock_start_stop(self):
        """Test mock can be started and stopped"""
        mock = MockWakeWordDetector()
        
        mock.start()
        time.sleep(0.1)
        
        assert mock.is_running() is True
        
        mock.stop()
        time.sleep(0.1)
        
        assert mock.is_running() is False


class TestWakeWordDetectorThreading:
    """Tests for WakeWordDetector threading behavior"""
    
    def test_detector_is_daemon_thread(self):
        """Test detector thread is a daemon"""
        detector = WakeWordDetector()
        assert detector.daemon is True
    
    def test_mock_is_daemon_thread(self):
        """Test mock detector thread is a daemon"""
        mock = MockWakeWordDetector()
        assert mock.daemon is True
    
    def test_stop_before_start_is_safe(self):
        """Test calling stop before start doesn't raise"""
        detector = WakeWordDetector()
        detector.stop()
    
    def test_multiple_stops_are_safe(self):
        """Test calling stop multiple times is safe"""
        mock = MockWakeWordDetector()
        mock.start()
        time.sleep(0.1)
        
        mock.stop()
        mock.stop()
        mock.stop()


class TestWakeWordDetectorWithSpeaker:
    """Tests for WakeWordDetector with speaker integration"""
    
    def test_speaker_initialization(self):
        """Test detector accepts speaker parameter"""
        class MockSpeaker:
            def beep(self, frequency=800, duration=200):
                pass
        
        speaker = MockSpeaker()
        detector = WakeWordDetector(speaker=speaker)
        
        assert detector.speaker is speaker
    
    def test_mock_simulate_detection_with_speaker(self):
        """Test simulate_detection calls speaker beep"""
        class MockSpeaker:
            beep_called = False
            
            def beep(self, frequency=800, duration=200):
                self.beep_called = True
        
        speaker = MockSpeaker()
        mock = MockWakeWordDetector(speaker=speaker)
        
        mock.simulate_detection()
        
        assert speaker.beep_called is True


class TestWakeWordDetectorEdgeCases:
    """Tests for edge cases and error handling"""
    
    def test_callback_with_exception_doesnt_crash(self):
        """Test callback exception doesn't crash detector"""
        mock = MockWakeWordDetector()
        results = []
        
        def bad_callback(d):
            raise ValueError("Test error")
        
        def good_callback(d):
            results.append("good")
        
        mock.on_wake_word(bad_callback)
        mock.on_wake_word(good_callback)
        
        with pytest.raises(ValueError):
            mock.simulate_detection()
    
    def test_empty_model_path_uses_default(self):
        """Test empty model path falls back to default"""
        detector = WakeWordDetector(model_path=None)
        assert detector.model_path == DEFAULT_MODEL_PATH
    
    def test_empty_engine_path_uses_default(self):
        """Test empty engine path falls back to default"""
        detector = WakeWordDetector(engine_path=None)
        assert detector.engine_path == DEFAULT_ENGINE_PATH


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
