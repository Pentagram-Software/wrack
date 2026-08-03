"""Unit tests for pipeline.py (PEN-193, tasks 1.4, 6.7, 7.1).

Uses duck-typed fakes for the detector/embedding backbone (no real ONNX
model or onnxruntime needed) and a real CatEventLifecycle/CatIdentifier so
the actual state-machine and distance logic are exercised end-to-end.
"""

import numpy as np
import pytest

from detection.detector import DetectionResult
from events.lifecycle import CatEventLifecycle, LifecycleConfig
from identification.identifier import CatIdentifier
from pipeline import VisionPipeline


class _ScriptedDetector:
    """Returns one DetectionResult per call, from a fixed script."""

    def __init__(self, results):
        self._results = list(results)
        self.call_count = 0

    def infer(self, frame):
        result = self._results[self.call_count]
        self.call_count += 1
        return result


class _ScriptedClock:
    def __init__(self, timestamps):
        self._timestamps = list(timestamps)
        self._i = 0

    def __call__(self):
        t = self._timestamps[self._i]
        self._i += 1
        return t


class _FakeEmbeddingBackbone:
    """Maps a crop's mean pixel value to a 2D unit vector, so different
    crops can be steered toward different identifier prototypes."""

    def embed(self, crop):
        brightness = float(crop.mean()) / 255.0 if crop.size else 0.0
        vector = np.array([brightness, 1.0 - brightness], dtype=np.float32)
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector


def _frame_source(frames):
    frames = list(frames)

    def _source():
        if not frames:
            return None
        return frames.pop(0)

    return _source


PRESENT = lambda conf=0.9: DetectionResult(present=True, confidence=conf, crop_bbox=(0.1, 0.1, 0.5, 0.5))
ABSENT = DetectionResult(present=False, confidence=0.0, crop_bbox=None)


class TestPhase1NoIdentification:
    def test_confirmed_and_closed_event_is_sent_with_unknown_identity(self):
        detector = _ScriptedDetector([PRESENT(), PRESENT(), PRESENT(), ABSENT, ABSENT])
        clock = _ScriptedClock([0.0, 0.33, 0.66, 1.0, 11.0])  # cooldown default 30s not needed w/ short config
        lifecycle = CatEventLifecycle(LifecycleConfig(confirmation_frames=3, absence_cooldown_seconds=10.0, detection_fps=3.0))
        sent = []
        pipeline = VisionPipeline(
            detector,
            _frame_source([np.zeros((10, 10, 3), dtype=np.uint8)] * 5),
            lifecycle=lifecycle,
            device_id="rpi-camera-01",
            model_version="yolov8n-1.0.0",
            pipeline_version="edge-vision-0.1.0",
            send_event=sent.append,
            clock=clock,
        )

        results = [pipeline.run_once() for _ in range(5)]

        assert results[:2] == [None, None]
        assert results[2] is None  # "started" transition — V1 doesn't emit yet
        assert results[3] is None  # absence within cooldown
        assert results[4] is not None  # absence >= cooldown -> closed + emitted

        assert len(sent) == 1
        payload = sent[0]["payload"]
        assert payload["predicted_identity"] == "unknown"
        assert payload["final_identity"] == "unknown"
        assert payload["identification_confidence"] is None
        assert payload["event_end_time"] is not None

    def test_isolated_frame_never_produces_an_event(self):
        detector = _ScriptedDetector([PRESENT(), ABSENT])
        clock = _ScriptedClock([0.0, 0.33])
        sent = []
        pipeline = VisionPipeline(
            detector,
            _frame_source([np.zeros((10, 10, 3), dtype=np.uint8)] * 2),
            device_id="rpi-camera-01",
            model_version="v1",
            pipeline_version="v1",
            send_event=sent.append,
            clock=clock,
        )

        pipeline.run_once()
        pipeline.run_once()

        assert sent == []

    def test_frame_source_returning_none_is_a_no_op(self):
        detector = _ScriptedDetector([])
        pipeline = VisionPipeline(
            detector,
            lambda: None,
            device_id="rpi-camera-01",
            model_version="v1",
            pipeline_version="v1",
        )
        assert pipeline.run_once() is None
        assert detector.call_count == 0


class TestPhase2WithIdentification:
    def test_closed_event_carries_real_identity(self):
        detector = _ScriptedDetector([PRESENT(), PRESENT(), PRESENT(), ABSENT, ABSENT])
        clock = _ScriptedClock([0.0, 0.33, 0.66, 1.0, 11.0])
        lifecycle = CatEventLifecycle(LifecycleConfig(confirmation_frames=3, absence_cooldown_seconds=10.0, detection_fps=3.0))
        identifier = CatIdentifier(
            {"ryfka": np.array([1.0, 0.0], dtype=np.float32), "chaja": np.array([0.0, 1.0], dtype=np.float32)},
            confidence_threshold=0.5,
        )
        bright_frame = np.full((10, 10, 3), 255, dtype=np.uint8)  # brightness -> [1.0, 0.0]-ish -> ryfka
        frames = [bright_frame, bright_frame, bright_frame, bright_frame, bright_frame]
        sent = []

        pipeline = VisionPipeline(
            detector,
            _frame_source(frames),
            lifecycle=lifecycle,
            embedding_backbone=_FakeEmbeddingBackbone(),
            identifier=identifier,
            device_id="rpi-camera-01",
            model_version="yolov8n-1.0.0",
            pipeline_version="edge-vision-0.1.0",
            send_event=sent.append,
            clock=clock,
        )

        for _ in range(5):
            pipeline.run_once()

        assert len(sent) == 1
        payload = sent[0]["payload"]
        assert payload["predicted_identity"] == "ryfka"
        assert payload["final_identity"] == "ryfka"
        assert payload["identification_confidence"] is not None

    def test_identification_resets_between_events(self):
        """A second, later event must not inherit the first event's
        identification result if nothing was identified on its own frames
        (regression guard for stale _last_identification state)."""
        clock = _ScriptedClock([0.0, 0.33, 0.66, 1.0, 11.0, 11.33, 11.66, 12.0, 12.33, 23.0])
        lifecycle = CatEventLifecycle(LifecycleConfig(confirmation_frames=3, absence_cooldown_seconds=10.0, detection_fps=3.0))
        identifier = CatIdentifier({"ryfka": np.array([1.0, 0.0], dtype=np.float32)}, confidence_threshold=0.9)

        # Event 2's "present" frames carry no crop_bbox, so process_frame's
        # `detection.crop_bbox is not None` guard skips identification for
        # them entirely — isolating whether _last_identification correctly
        # resets to None after event 1 closes, versus leaking into event 2.
        detector = _ScriptedDetector(
            [
                PRESENT(), PRESENT(), PRESENT(),
                ABSENT, ABSENT,
                DetectionResult(present=True, confidence=0.9, crop_bbox=None),
                DetectionResult(present=True, confidence=0.9, crop_bbox=None),
                DetectionResult(present=True, confidence=0.9, crop_bbox=None),
                ABSENT, ABSENT,
            ]
        )
        # Bright frames -> brightness-based fake embedding lands near
        # ryfka's [1.0, 0.0] prototype whenever identification does run.
        bright_frame = np.full((10, 10, 3), 255, dtype=np.uint8)
        sent = []
        pipeline = VisionPipeline(
            detector,
            _frame_source([bright_frame] * 10),
            lifecycle=lifecycle,
            embedding_backbone=_FakeEmbeddingBackbone(),
            identifier=identifier,
            device_id="rpi-camera-01",
            model_version="v1",
            pipeline_version="v1",
            send_event=sent.append,
            clock=clock,
        )

        for _ in range(10):
            pipeline.run_once()

        assert len(sent) == 2
        assert sent[0]["payload"]["final_identity"] == "ryfka"
        # Event 2 had no crop_bbox on any frame -> identification never ran -> unknown.
        assert sent[1]["payload"]["predicted_identity"] == "unknown"
        assert sent[1]["payload"]["final_identity"] == "unknown"


class TestConstructorValidation:
    def test_rejects_embedding_backbone_without_identifier(self):
        with pytest.raises(ValueError):
            VisionPipeline(
                _ScriptedDetector([]),
                lambda: None,
                embedding_backbone=_FakeEmbeddingBackbone(),
                identifier=None,
                device_id="d",
                model_version="v",
                pipeline_version="v",
            )

    def test_rejects_identifier_without_embedding_backbone(self):
        with pytest.raises(ValueError):
            VisionPipeline(
                _ScriptedDetector([]),
                lambda: None,
                embedding_backbone=None,
                identifier=CatIdentifier({"ryfka": np.array([1.0, 0.0], dtype=np.float32)}),
                device_id="d",
                model_version="v",
                pipeline_version="v",
            )


class TestRunForever:
    def test_calls_run_once_max_iterations_times_and_sleeps_between(self, monkeypatch):
        sleep_calls = []
        monkeypatch.setattr("pipeline.time.sleep", lambda s: sleep_calls.append(s))

        detector = _ScriptedDetector([ABSENT, ABSENT, ABSENT])
        pipeline = VisionPipeline(
            detector,
            _frame_source([np.zeros((10, 10, 3), dtype=np.uint8)] * 3),
            device_id="d",
            model_version="v",
            pipeline_version="v",
        )

        pipeline.run_forever(fps=3.0, max_iterations=3)

        assert detector.call_count == 3
        # Sleeps between calls only, not after the last one.
        assert len(sleep_calls) == 2
        assert sleep_calls[0] == pytest.approx(1.0 / 3.0)


class TestExtractCrop:
    def test_crop_bounds_clipped_to_frame(self):
        detector = _ScriptedDetector([])
        pipeline = VisionPipeline(
            detector,
            lambda: None,
            device_id="d",
            model_version="v",
            pipeline_version="v",
        )
        frame = np.arange(100 * 100 * 3, dtype=np.uint8).reshape(100, 100, 3)
        crop = pipeline._extract_crop(frame, (0.0, 0.0, 1.0, 1.0))
        assert crop.shape == (100, 100, 3)

    def test_partial_bbox_extracts_expected_region(self):
        detector = _ScriptedDetector([])
        pipeline = VisionPipeline(
            detector,
            lambda: None,
            device_id="d",
            model_version="v",
            pipeline_version="v",
        )
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        crop = pipeline._extract_crop(frame, (0.25, 0.5, 0.75, 1.0))
        # x: 0.25*200=50 to 0.75*200=150 -> width 100; y: 0.5*100=50 to 100 -> height 50
        assert crop.shape == (50, 100, 3)
