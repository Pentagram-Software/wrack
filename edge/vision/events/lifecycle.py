"""Cat event lifecycle state machine (PEN-243–246, tasks 2.1-2.4).

Implements the ``cat-event-lifecycle`` spec:

- **Multi-Frame Event Confirmation**: an event starts only after 3
  consecutive detected frames; a break in consecutive detections resets the
  confirmation counter.
- **Active Event Persistence**: once confirmed, an event stays active while
  presence continues.
- **Configurable Absence Cooldown**: an active event ends only after
  presence has been absent for a configurable cooldown; a brief absence
  shorter than the cooldown does not split the event.

Purely a frame-driven state machine — no I/O, no clock of its own. It is
fed one frame's ``(detected, confidence, now)`` observation at a time (from
the Pi-side inference loop, task 1.4/6.7), and reacts only to what it's told;
it is *not* a background timer. Cooldown expiry is therefore detected the
next time an absent frame is observed, not at a precise wall-clock instant —
correct for a continuously-polled loop (frames arrive every
``1 / detection_fps`` seconds; at the default 3 FPS, a cooldown that just
elapsed is caught on the very next observed frame, well before an
after-the-fact "presence resumed" call could silently skip over a closed
gap).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


class LifecycleConfig:
    """Externally configurable lifecycle parameters (task 2.4, PRD §8).

    Each parameter falls back to an environment variable, then a default,
    matching the ``os.environ.get(...)`` convention already used by
    ``telemetry/sender.py``. Explicit constructor args always win.
    """

    def __init__(
        self,
        confirmation_frames: Optional[int] = None,
        absence_cooldown_seconds: Optional[float] = None,
        detection_fps: Optional[float] = None,
    ) -> None:
        self.confirmation_frames = (
            confirmation_frames
            if confirmation_frames is not None
            else int(os.environ.get("CAT_CONFIRMATION_FRAMES", 3))
        )
        self.absence_cooldown_seconds = (
            absence_cooldown_seconds
            if absence_cooldown_seconds is not None
            else float(os.environ.get("CAT_ABSENCE_COOLDOWN_SECONDS", 30.0))
        )
        self.detection_fps = (
            detection_fps
            if detection_fps is not None
            else float(os.environ.get("CAT_DETECTION_FPS", 3.0))
        )

        if self.confirmation_frames < 1:
            raise ValueError("confirmation_frames must be at least 1")
        if self.absence_cooldown_seconds < 0:
            raise ValueError("absence_cooldown_seconds must not be negative")
        if self.detection_fps <= 0:
            raise ValueError("detection_fps must be positive")


@dataclass(frozen=True)
class EventTransition:
    """Returned by :meth:`CatEventLifecycle.observe` exactly when an event
    starts or ends this frame; ``None`` (no transition) otherwise."""

    kind: str  # "started" | "ended"
    start_time: float
    end_time: Optional[float] = None
    confidence: float = 0.0


class CatEventLifecycle:
    """Turns a stream of per-frame detection results into discrete,
    confirmed events (cat-event-lifecycle spec)."""

    def __init__(self, config: Optional[LifecycleConfig] = None) -> None:
        self.config = config or LifecycleConfig()
        self._consecutive_detected = 0
        self._pending_start_time: Optional[float] = None
        self._event_active = False
        self._event_start_time: Optional[float] = None
        self._absence_start_time: Optional[float] = None
        self._last_confidence = 0.0

    @property
    def is_active(self) -> bool:
        return self._event_active

    def observe(self, *, detected: bool, confidence: float, now: float) -> Optional[EventTransition]:
        """Feed one frame's detection result. Returns an
        :class:`EventTransition` when an event starts or ends this frame."""
        if detected:
            return self._observe_detected(confidence, now)
        return self._observe_absent(now)

    def _observe_detected(self, confidence: float, now: float) -> Optional[EventTransition]:
        # Presence resumed cancels any in-progress absence/cooldown clock.
        self._absence_start_time = None
        self._last_confidence = confidence

        if self._event_active:
            return None

        self._consecutive_detected += 1
        if self._consecutive_detected == 1:
            self._pending_start_time = now

        if self._consecutive_detected < self.config.confirmation_frames:
            return None

        self._event_active = True
        self._event_start_time = self._pending_start_time
        self._consecutive_detected = 0
        return EventTransition(kind="started", start_time=self._event_start_time, confidence=confidence)

    def _observe_absent(self, now: float) -> Optional[EventTransition]:
        if not self._event_active:
            # Isolated/unconfirmed detections don't survive a gap.
            self._consecutive_detected = 0
            return None

        if self._absence_start_time is None:
            self._absence_start_time = now

        if now - self._absence_start_time < self.config.absence_cooldown_seconds:
            return None

        transition = EventTransition(
            kind="ended",
            start_time=self._event_start_time,  # type: ignore[arg-type]
            end_time=self._absence_start_time,
            confidence=self._last_confidence,
        )
        self._reset()
        return transition

    def _reset(self) -> None:
        self._consecutive_detected = 0
        self._pending_start_time = None
        self._event_active = False
        self._event_start_time = None
        self._absence_start_time = None
        self._last_confidence = 0.0
