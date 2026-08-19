"""Unit tests for detection/export_model.py's CANDIDATES mapping (PEN-238/239).

Regression guard for the yolov5n/YOLOv5u decoder mismatch: the `ultralytics`
package's `yolov5n.pt` weights are YOLOv5u (anchor-free, v8-style head), so
its ONNX export must be paired with decode_yolov8_output, not
decode_yolov5_output (the classic YOLOv5 [1, N, 85] head) — see
MODEL_SELECTION.md's "Candidate B" note. No `ultralytics`/`torch` needed:
this only inspects the static mapping, not `export()` itself.
"""

from detection.export_model import CANDIDATES


def test_yolov5n_candidate_uses_yolov8_decoder():
    """ultralytics' yolov5n.pt is YOLOv5u under the hood — its ONNX export
    is the [1, 84, N] anchor-free shape, not the classic [1, N, 85] head."""
    assert CANDIDATES["yolov5n"]["decoder"] == "yolov8"


def test_yolov8n_candidate_uses_yolov8_decoder():
    assert CANDIDATES["yolov8n"]["decoder"] == "yolov8"


def test_all_candidates_reference_a_pt_weights_file():
    for candidate, config in CANDIDATES.items():
        assert config["weights"].endswith(".pt"), candidate
