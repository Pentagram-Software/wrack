"""Unit tests for identification/embeddings.py (PEN-260, task 6.1)."""

import numpy as np
import pytest

from identification.embeddings import EmbeddingBackbone, l2_normalize


class TestL2Normalize:
    def test_unit_length_after_normalization(self):
        vector = np.array([3.0, 4.0], dtype=np.float32)
        normalized = l2_normalize(vector)
        assert np.linalg.norm(normalized) == pytest.approx(1.0)

    def test_direction_preserved(self):
        vector = np.array([3.0, 4.0], dtype=np.float32)
        normalized = l2_normalize(vector)
        assert normalized[0] == pytest.approx(0.6)
        assert normalized[1] == pytest.approx(0.8)

    def test_zero_vector_returned_unchanged(self):
        vector = np.zeros(4, dtype=np.float32)
        assert np.array_equal(l2_normalize(vector), vector)


class _FakeInput:
    name = "input"


class _FakeSession:
    def __init__(self, output_vector):
        self._output_vector = output_vector
        self.last_feed = None

    def get_inputs(self):
        return [_FakeInput()]

    def run(self, output_names, feed_dict):
        self.last_feed = feed_dict
        return [self._output_vector]


class TestEmbeddingBackbone:
    def _make_backbone(self, output_vector, **kwargs):
        session = _FakeSession(output_vector)
        return (
            EmbeddingBackbone("unused-model.onnx", session_factory=lambda path: session, **kwargs),
            session,
        )

    def test_embed_returns_l2_normalized_vector(self):
        raw = np.array([[3.0, 4.0]], dtype=np.float32)  # [1, 2] batch output
        backbone, _ = self._make_backbone(raw)
        crop = np.zeros((100, 100, 3), dtype=np.uint8)

        embedding = backbone.embed(crop)

        assert np.linalg.norm(embedding) == pytest.approx(1.0)
        assert embedding[0] == pytest.approx(0.6)
        assert embedding[1] == pytest.approx(0.8)

    def test_preprocess_resizes_and_feeds_input_name(self):
        raw = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
        backbone, session = self._make_backbone(raw, input_size=(224, 224))
        crop = np.zeros((50, 80, 3), dtype=np.uint8)

        backbone.embed(crop)

        assert "input" in session.last_feed
        fed = session.last_feed["input"]
        assert fed.shape == (1, 3, 224, 224)
        assert fed.dtype == np.float32

    def test_different_crops_can_produce_different_embeddings(self):
        """Sanity check that preprocessing doesn't collapse all inputs to
        one constant feed — regression guard for a broken normalization
        step that would make every crop look identical to the backbone."""
        session_outputs = []

        class _RecordingSession(_FakeSession):
            def run(self, output_names, feed_dict):
                session_outputs.append(feed_dict["input"].copy())
                return [self._output_vector]

        session = _RecordingSession(np.array([[1.0, 0.0]], dtype=np.float32))
        backbone = EmbeddingBackbone("unused.onnx", session_factory=lambda path: session)

        dark_crop = np.zeros((100, 100, 3), dtype=np.uint8)
        light_crop = np.full((100, 100, 3), 255, dtype=np.uint8)
        backbone.embed(dark_crop)
        backbone.embed(light_crop)

        assert not np.array_equal(session_outputs[0], session_outputs[1])
