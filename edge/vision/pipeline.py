"""Vision pipeline orchestration (PEN-193, tasks 1.4, 6.7, 7.1).

Wires together, per sampled frame:

- :class:`detection.detector.CatDetector` — presence/confidence/crop
- :class:`events.lifecycle.CatEventLifecycle` — confirms/closes discrete
  events from the stream of per-frame detection results
- :class:`identification.identifier.CatIdentifier` (with an
  :class:`identification.embeddings.EmbeddingBackbone` to produce the
  embedding it compares), **optional** — Phase 2's real identity. Omitting
  both (Phase 1) leaves every emitted event's identity fixed to
  ``"unknown"``; providing both (Phase 2, task 7.1) replaces that fixed
  value with real identification output, without any other code changing.
- :func:`telemetry.builder.build_cat_detection_event` + a ``send_event``
  callback — cloud emission, once per event, at close.

Frames are supplied via a pluggable ``frame_source`` callable (task 1.4's
"reading frames from edge/video-streamer/'s existing capture path" — this
module deliberately does not open a camera itself; wire ``frame_source`` to
whatever shared capture path `edge/video-streamer/` exposes once that
integration point is built, so detection and streaming never open two
camera sessions).
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np

from detection.detector import CatDetector
from events.lifecycle import CatEventLifecycle, EventTransition
from identification.embeddings import EmbeddingBackbone
from identification.identifier import CatIdentifier, IdentificationResult
from telemetry.builder import build_cat_detection_event

FrameSource = Callable[[], Optional[np.ndarray]]
EventSender = Callable[[dict], None]


def _iso8601(timestamp: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(timestamp)) + "Z"


class VisionPipeline:
    """Runs detection (+ optionally identification) against frames from
    ``frame_source``, emitting one ``cat_detection`` telemetry event per
    confirmed-and-closed cat event.

    Parameters
    ----------
    detector, frame_source:
        See module docstring.
    lifecycle:
        Defaults to a fresh :class:`CatEventLifecycle` (its own
        :class:`LifecycleConfig` reads FPS/confirmation/cooldown from
        environment variables — task 2.4).
    embedding_backbone, identifier:
        Phase 2 only — both or neither. Passing both wires identification
        into the loop (task 6.7) and into emitted events (task 7.1);
        leaving both ``None`` (Phase 1) keeps every event's identity fixed
        to ``"unknown"``.
    device_id, model_version, pipeline_version:
        Forwarded to every built event — see ``cat_detection.json``.
    send_event:
        Called with the built event dict when an event closes — typically
        ``RpiTelemetrySender.send_events`` wrapped to take one event, or a
        collector's ``collect_raw``. ``None`` disables sending (useful for
        tests / dry runs); the built event is still returned either way.
    clock:
        Returns the current time as a float epoch seconds. Overridable for
        deterministic tests.
    """

    def __init__(
        self,
        detector: CatDetector,
        frame_source: FrameSource,
        *,
        lifecycle: Optional[CatEventLifecycle] = None,
        embedding_backbone: Optional[EmbeddingBackbone] = None,
        identifier: Optional[CatIdentifier] = None,
        device_id: str,
        model_version: str,
        pipeline_version: str,
        send_event: Optional[EventSender] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if (embedding_backbone is None) != (identifier is None):
            raise ValueError(
                "embedding_backbone and identifier must both be provided (Phase 2) "
                "or both omitted (Phase 1) — partial identification wiring isn't supported"
            )

        self.detector = detector
        self.frame_source = frame_source
        self.lifecycle = lifecycle or CatEventLifecycle()
        self.embedding_backbone = embedding_backbone
        self.identifier = identifier
        self.device_id = device_id
        self.model_version = model_version
        self.pipeline_version = pipeline_version
        self.send_event = send_event
        self.clock = clock

        # Most recent identification result for the currently-active event,
        # reset when that event closes — so the event built at close time
        # reflects identification from while the cat was actually present,
        # not from whatever ran on an unrelated later frame.
        self._last_identification: Optional[IdentificationResult] = None

    def run_once(self) -> Optional[dict]:
        """Pull one frame from ``frame_source`` and process it. Returns the
        built (and, if ``send_event`` is set, sent) event dict if this frame
        closed an event, else ``None`` — including when ``frame_source``
        has no frame ready."""
        frame = self.frame_source()
        if frame is None:
            return None
        return self.process_frame(frame)

    def run_forever(self, *, fps: Optional[float] = None, max_iterations: Optional[int] = None) -> None:
        """Call :meth:`run_once` in a loop at ``fps`` (task 1.4's
        "configurable FPS, default 3"), sleeping between calls. Defaults to
        ``self.lifecycle.config.detection_fps``. ``max_iterations`` bounds
        the loop for tests / bring-up runs; omit it to run indefinitely."""
        rate = fps if fps is not None else self.lifecycle.config.detection_fps
        interval = 1.0 / rate
        count = 0
        while max_iterations is None or count < max_iterations:
            self.run_once()
            count += 1
            if max_iterations is None or count < max_iterations:
                time.sleep(interval)

    def process_frame(self, frame: np.ndarray) -> Optional[dict]:
        """Run detection (+ identification, if wired in) on ``frame``, feed
        the lifecycle state machine, and emit a ``cat_detection`` event if
        this frame closed one."""
        detection = self.detector.infer(frame)
        now = self.clock()

        if detection.present and self.identifier is not None and detection.crop_bbox is not None:
            crop = self._extract_crop(frame, detection.crop_bbox)
            embedding = self.embedding_backbone.embed(crop)  # type: ignore[union-attr]
            self._last_identification = self.identifier.identify(embedding)

        transition = self.lifecycle.observe(
            detected=detection.present, confidence=detection.confidence, now=now
        )
        if transition is None:
            return None
        if transition.kind == "started":
            # V1 emits once, at close (see telemetry/builder.py's
            # build_cat_detection_event docstring) — nothing to send yet.
            return None

        event = self._build_event(transition)
        if self.send_event is not None:
            self.send_event(event)
        self._last_identification = None  # next event starts with no identification yet
        return event

    def _extract_crop(self, frame: np.ndarray, bbox) -> np.ndarray:
        """Slice out the detected region and convert BGR (OpenCV, what
        ``frame_source`` yields) -> RGB, matching the convention
        ``identification/enroll.py`` already uses for enrollment photos —
        without this, live crops and enrolled prototypes would be embedded
        in different color spaces, degrading cosine similarity."""
        height, width = frame.shape[:2]
        x_min, y_min, x_max, y_max = bbox
        x1, y1 = max(0, int(x_min * width)), max(0, int(y_min * height))
        x2, y2 = min(width, int(x_max * width)), min(height, int(y_max * height))
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return crop
        import cv2

        return cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

    def _build_event(self, transition: EventTransition) -> dict:
        if self._last_identification is not None:
            predicted_identity = self._last_identification.predicted_identity
            final_identity = self._last_identification.final_identity
            identification_confidence = self._last_identification.identification_confidence
        else:
            predicted_identity = "unknown"
            final_identity = "unknown"
            identification_confidence = None

        return build_cat_detection_event(
            event_start_time=_iso8601(transition.start_time),
            event_end_time=_iso8601(transition.end_time) if transition.end_time is not None else None,
            detection_confidence=transition.confidence,
            device_id=self.device_id,
            model_version=self.model_version,
            pipeline_version=self.pipeline_version,
            predicted_identity=predicted_identity,
            final_identity=final_identity,
            identification_confidence=identification_confidence,
        )
