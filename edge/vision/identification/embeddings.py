"""ONNX embedding backbone wrapper for cat identification (PEN-193, task 6.1).

Wraps an ONNX Runtime session for the backbone picked in
``MODEL_SELECTION.md``, turning one detected cat crop into a single
L2-normalized feature vector. Like ``detection/detector.py``, ``onnxruntime``
is only imported inside the default session factory so this module stays
testable without the Pi's inference runtime installed.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

import numpy as np

#: Standard ImageNet normalization constants, since the backbone (whichever
#: torchvision/ImageNet-pretrained model MODEL_SELECTION.md's export step
#: produces) expects inputs normalized this way.
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    """L2-normalize *vector*; returns the zero vector unchanged rather than
    dividing by zero."""
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


class EmbeddingBackbone:
    """Runs one ONNX embedding backbone against cat crops.

    Parameters
    ----------
    model_path:
        Path to the exported ONNX model (see ``MODEL_SELECTION.md``).
    input_size:
        ``(width, height)`` the model expects. Defaults to ``(224, 224)``
        (the standard ImageNet-pretrained input size).
    session_factory:
        Builds the ONNX Runtime session from ``model_path``. Defaults to a
        real ``onnxruntime.InferenceSession`` (imported lazily). Tests
        inject a fake session here.
    """

    def __init__(
        self,
        model_path: str,
        *,
        input_size: Tuple[int, int] = (224, 224),
        session_factory: Optional[Callable[[str], object]] = None,
    ) -> None:
        session_factory = session_factory or self._default_session_factory
        self._session = session_factory(model_path)
        self._input_name = self._session.get_inputs()[0].name
        self.input_size = input_size

    @staticmethod
    def _default_session_factory(model_path: str):
        import onnxruntime as ort  # local import — see class docstring

        return ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    def embed(self, crop: np.ndarray) -> np.ndarray:
        """Return an L2-normalized embedding vector for one RGB ``crop``
        (H, W, 3)."""
        preprocessed = self._preprocess(crop)
        outputs = self._session.run(None, {self._input_name: preprocessed})
        vector = np.asarray(outputs[0], dtype=np.float32).reshape(-1)
        return l2_normalize(vector)

    def _preprocess(self, crop: np.ndarray) -> np.ndarray:
        """Resize to ``input_size``, scale to [0, 1], apply ImageNet
        mean/std normalization, convert HWC -> NCHW."""
        import cv2

        resized = cv2.resize(crop, self.input_size)
        scaled = resized.astype(np.float32) / 255.0
        normalized = (scaled - _IMAGENET_MEAN) / _IMAGENET_STD
        chw = normalized.transpose(2, 0, 1)
        return np.expand_dims(chw, axis=0).astype(np.float32)
