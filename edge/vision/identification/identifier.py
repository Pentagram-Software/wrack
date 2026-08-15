"""Distance-based cat identification against enrolled prototypes
(PEN-264/PEN-265, tasks 6.5-6.6).

Implements the ``cat-identification`` spec's "Known-Cat Identity Prediction"
and "Identity Confidence Threshold and Unknown Fallback" requirements:
compare a detected crop's embedding to every enrolled prototype by cosine
similarity, the closest one is the top predicted identity, and the final
identity falls back to ``unknown`` below a configurable threshold while
still preserving the predicted identity for later analysis.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

#: Default minimum cosine similarity for final_identity to equal the top
#: predicted identity, used when neither an explicit constructor arg nor
#: the CAT_IDENTITY_CONFIDENCE_THRESHOLD env var is set.
DEFAULT_CONFIDENCE_THRESHOLD = 0.6


@dataclass(frozen=True)
class IdentificationResult:
    predicted_identity: str
    identification_confidence: float
    final_identity: str


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class CatIdentifier:
    """Identifies a cat crop's embedding against a fixed set of enrolled
    prototypes (see ``enroll.py``).

    Parameters
    ----------
    prototypes:
        Cat name -> prototype embedding vector (from
        :func:`enroll.load_prototypes`). Must contain at least one entry.
    confidence_threshold:
        Minimum cosine similarity for ``final_identity`` to equal the top
        predicted identity; below it, ``final_identity`` is ``"unknown"``.
        Provisional per ``design.md``'s open question on threshold
        validation — pass the value from task 6.8's sanity check once run.
        Falls back to the CAT_IDENTITY_CONFIDENCE_THRESHOLD environment
        variable, then DEFAULT_CONFIDENCE_THRESHOLD, matching the
        env-var-configurable convention established by
        ``detection.detector.CatDetector``'s confidence_threshold — so a
        threshold picked by ``evaluate_threshold.py`` can be applied to
        ``soak_test.py`` without editing code.
    """

    def __init__(
        self,
        prototypes: Dict[str, np.ndarray],
        confidence_threshold: Optional[float] = None,
    ) -> None:
        if not prototypes:
            raise ValueError("CatIdentifier requires at least one enrolled prototype")
        resolved_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else float(os.environ.get("CAT_IDENTITY_CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD))
        )
        if not (0 <= resolved_threshold <= 1):
            raise ValueError("confidence_threshold must be between 0 and 1")
        self.prototypes = prototypes
        self.confidence_threshold = resolved_threshold

    def identify(self, embedding: np.ndarray) -> IdentificationResult:
        similarities = {
            name: cosine_similarity(embedding, prototype)
            for name, prototype in self.prototypes.items()
        }
        predicted_identity = max(similarities, key=similarities.get)
        # Cosine similarity of two L2-normalized vectors is in [-1, 1] in
        # general, but for these non-negative pixel-derived embeddings it's
        # effectively in [0, 1] — clamp defensively against float drift
        # rather than assuming the theoretical bound holds exactly.
        confidence = max(0.0, min(1.0, similarities[predicted_identity]))
        final_identity = (
            predicted_identity if confidence >= self.confidence_threshold else "unknown"
        )
        return IdentificationResult(
            predicted_identity=predicted_identity,
            identification_confidence=confidence,
            final_identity=final_identity,
        )
