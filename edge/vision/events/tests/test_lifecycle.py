"""Unit tests for events/lifecycle.py, one per cat-event-lifecycle spec
scenario (PEN-243–246, tasks 2.1-2.4)."""

import pytest

from events.lifecycle import CatEventLifecycle, LifecycleConfig


def _config(**overrides):
    kwargs = {"confirmation_frames": 3, "absence_cooldown_seconds": 10.0, "detection_fps": 3.0}
    kwargs.update(overrides)
    return LifecycleConfig(**kwargs)


class TestLifecycleConfig:
    def test_defaults(self):
        config = LifecycleConfig()
        assert config.confirmation_frames == 3
        assert config.absence_cooldown_seconds == 30.0
        assert config.detection_fps == 3.0

    def test_env_vars_override_defaults(self, monkeypatch):
        monkeypatch.setenv("CAT_CONFIRMATION_FRAMES", "5")
        monkeypatch.setenv("CAT_ABSENCE_COOLDOWN_SECONDS", "45.5")
        monkeypatch.setenv("CAT_DETECTION_FPS", "6")
        config = LifecycleConfig()
        assert config.confirmation_frames == 5
        assert config.absence_cooldown_seconds == 45.5
        assert config.detection_fps == 6.0

    def test_explicit_args_win_over_env(self, monkeypatch):
        monkeypatch.setenv("CAT_CONFIRMATION_FRAMES", "5")
        config = LifecycleConfig(confirmation_frames=2)
        assert config.confirmation_frames == 2

    def test_rejects_zero_confirmation_frames(self):
        with pytest.raises(ValueError):
            LifecycleConfig(confirmation_frames=0)

    def test_rejects_negative_cooldown(self):
        with pytest.raises(ValueError):
            LifecycleConfig(absence_cooldown_seconds=-1)

    def test_rejects_non_positive_fps(self):
        with pytest.raises(ValueError):
            LifecycleConfig(detection_fps=0)


class TestIsolatedSingleFrameDetection:
    """Spec scenario: isolated single-frame detection does not create an event."""

    def test_no_event_on_single_frame_then_gap(self):
        lifecycle = CatEventLifecycle(_config())
        t1 = lifecycle.observe(detected=True, confidence=0.9, now=0.0)
        t2 = lifecycle.observe(detected=False, confidence=0.0, now=0.33)
        assert t1 is None
        assert t2 is None
        assert lifecycle.is_active is False

    def test_confirmation_counter_resets_on_break(self):
        lifecycle = CatEventLifecycle(_config())
        lifecycle.observe(detected=True, confidence=0.9, now=0.0)
        lifecycle.observe(detected=True, confidence=0.9, now=0.33)
        lifecycle.observe(detected=False, confidence=0.0, now=0.66)  # break
        # Only 2 consecutive after the break — must not confirm yet.
        t = lifecycle.observe(detected=True, confidence=0.9, now=1.0)
        assert t is None
        assert lifecycle.is_active is False


class TestThreeConsecutiveFramesConfirm:
    """Spec scenario: three consecutive frames confirm an event."""

    def test_event_starts_on_third_consecutive_frame(self):
        lifecycle = CatEventLifecycle(_config())
        t1 = lifecycle.observe(detected=True, confidence=0.8, now=0.0)
        t2 = lifecycle.observe(detected=True, confidence=0.85, now=0.33)
        t3 = lifecycle.observe(detected=True, confidence=0.9, now=0.66)
        assert t1 is None
        assert t2 is None
        assert t3 is not None
        assert t3.kind == "started"
        assert t3.start_time == 0.0  # start_time is the first confirming frame
        assert lifecycle.is_active is True

    def test_confirmation_frames_is_configurable(self):
        lifecycle = CatEventLifecycle(_config(confirmation_frames=2))
        t1 = lifecycle.observe(detected=True, confidence=0.8, now=0.0)
        t2 = lifecycle.observe(detected=True, confidence=0.8, now=0.33)
        assert t1 is None
        assert t2 is not None
        assert t2.kind == "started"


class TestActiveEventPersistence:
    """Spec scenario: continued presence keeps the event active."""

    def test_no_further_transitions_while_presence_continues(self):
        lifecycle = CatEventLifecycle(_config())
        for now in (0.0, 0.33, 0.66):
            lifecycle.observe(detected=True, confidence=0.9, now=now)
        assert lifecycle.is_active is True
        for now in (1.0, 1.33, 1.66, 2.0):
            transition = lifecycle.observe(detected=True, confidence=0.9, now=now)
            assert transition is None
        assert lifecycle.is_active is True


class TestConfigurableAbsenceCooldown:
    """Spec scenarios: brief absence doesn't end the event; absence
    exceeding cooldown ends it and allows a new one to start."""

    def _confirmed_lifecycle(self, cooldown_seconds):
        lifecycle = CatEventLifecycle(_config(absence_cooldown_seconds=cooldown_seconds))
        for now in (0.0, 0.33, 0.66):
            lifecycle.observe(detected=True, confidence=0.9, now=now)
        assert lifecycle.is_active is True
        return lifecycle

    def test_brief_absence_does_not_end_event(self):
        lifecycle = self._confirmed_lifecycle(cooldown_seconds=10.0)
        t1 = lifecycle.observe(detected=False, confidence=0.0, now=1.0)
        t2 = lifecycle.observe(detected=True, confidence=0.9, now=5.0)  # resumes within cooldown
        assert t1 is None
        assert t2 is None
        assert lifecycle.is_active is True

    def test_resumed_presence_within_cooldown_is_same_event_not_two(self):
        lifecycle = self._confirmed_lifecycle(cooldown_seconds=10.0)
        lifecycle.observe(detected=False, confidence=0.0, now=1.0)
        lifecycle.observe(detected=True, confidence=0.9, now=5.0)
        # No re-confirmation needed — still the original active event.
        assert lifecycle.is_active is True

    def test_absence_exceeding_cooldown_ends_event(self):
        lifecycle = self._confirmed_lifecycle(cooldown_seconds=10.0)
        lifecycle.observe(detected=False, confidence=0.0, now=1.0)  # absence starts at t=1.0
        t = lifecycle.observe(detected=False, confidence=0.0, now=12.0)  # 11s absence >= 10s cooldown
        assert t is not None
        assert t.kind == "ended"
        assert t.start_time == 0.0
        assert t.end_time == 1.0  # end_time is when presence was last observed, not when cooldown expired
        assert lifecycle.is_active is False

    def test_new_confirmed_detection_after_cooldown_starts_separate_event(self):
        lifecycle = self._confirmed_lifecycle(cooldown_seconds=10.0)
        lifecycle.observe(detected=False, confidence=0.0, now=1.0)
        ended = lifecycle.observe(detected=False, confidence=0.0, now=12.0)
        assert ended.kind == "ended"

        # A single detected frame right after must NOT immediately restart —
        # the new event needs its own 3-frame confirmation.
        t1 = lifecycle.observe(detected=True, confidence=0.9, now=12.33)
        assert t1 is None
        assert lifecycle.is_active is False

        t2 = lifecycle.observe(detected=True, confidence=0.9, now=12.66)
        t3 = lifecycle.observe(detected=True, confidence=0.9, now=13.0)
        assert t3.kind == "started"
        assert t3.start_time == 12.33
        assert lifecycle.is_active is True

    def test_cooldown_is_configurable(self):
        lifecycle = self._confirmed_lifecycle(cooldown_seconds=1.0)
        lifecycle.observe(detected=False, confidence=0.0, now=1.0)
        t = lifecycle.observe(detected=False, confidence=0.0, now=2.5)  # 1.5s >= 1.0s cooldown
        assert t.kind == "ended"
