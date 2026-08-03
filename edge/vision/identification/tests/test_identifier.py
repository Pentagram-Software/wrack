"""Unit tests for identification/identifier.py (PEN-193, tasks 6.5-6.6)."""

import numpy as np
import pytest

from identification.identifier import CatIdentifier, cosine_similarity


class TestCosineSimilarity:
    def test_identical_vectors_similarity_is_one(self):
        v = np.array([1.0, 0.0], dtype=np.float32)
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_similarity_is_zero(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_zero_vector_similarity_is_zero(self):
        a = np.zeros(2, dtype=np.float32)
        b = np.array([1.0, 0.0], dtype=np.float32)
        assert cosine_similarity(a, b) == 0.0


class TestCatIdentifier:
    def _prototypes(self):
        return {
            "ryfka": np.array([1.0, 0.0], dtype=np.float32),
            "chaja": np.array([0.0, 1.0], dtype=np.float32),
            "lea": np.array([-1.0, 0.0], dtype=np.float32),
        }

    def test_requires_at_least_one_prototype(self):
        with pytest.raises(ValueError):
            CatIdentifier({})

    def test_rejects_out_of_range_threshold(self):
        with pytest.raises(ValueError):
            CatIdentifier(self._prototypes(), confidence_threshold=1.5)

    def test_confident_match_sets_final_identity_to_predicted(self):
        identifier = CatIdentifier(self._prototypes(), confidence_threshold=0.6)
        embedding = np.array([1.0, 0.05], dtype=np.float32)  # close to ryfka's prototype

        result = identifier.identify(embedding)

        assert result.predicted_identity == "ryfka"
        assert result.final_identity == "ryfka"
        assert result.identification_confidence >= 0.6

    def test_low_confidence_falls_back_to_unknown_but_keeps_predicted(self):
        """Spec scenario: low-confidence match falls back to unknown, and
        the top predicted identity is still recorded."""
        identifier = CatIdentifier(self._prototypes(), confidence_threshold=0.99)
        embedding = np.array([1.0, 0.3], dtype=np.float32)  # closest to ryfka, but similarity ~0.96 < 0.99

        result = identifier.identify(embedding)

        assert result.predicted_identity == "ryfka"
        assert result.final_identity == "unknown"
        assert result.identification_confidence < 0.99

    def test_exactly_at_threshold_counts_as_confident(self):
        identifier = CatIdentifier({"ryfka": np.array([1.0, 0.0], dtype=np.float32)}, confidence_threshold=1.0)
        result = identifier.identify(np.array([1.0, 0.0], dtype=np.float32))
        assert result.final_identity == "ryfka"

    def test_closest_prototype_wins_among_several(self):
        identifier = CatIdentifier(self._prototypes(), confidence_threshold=0.0)
        embedding = np.array([0.0, 1.0], dtype=np.float32)  # matches chaja exactly
        result = identifier.identify(embedding)
        assert result.predicted_identity == "chaja"

    def test_confidence_clamped_to_zero_one_range(self):
        identifier = CatIdentifier(self._prototypes(), confidence_threshold=0.0)
        embedding = np.array([-1.0, 0.0], dtype=np.float32)  # matches lea exactly (similarity 1.0)
        result = identifier.identify(embedding)
        assert 0.0 <= result.identification_confidence <= 1.0
