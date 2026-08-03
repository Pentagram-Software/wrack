"""COCO class filtering for cat detection (PEN-193, task 1.1).

Both candidate detectors in ``MODEL_SELECTION.md`` are pretrained on the
standard 80-class COCO taxonomy, where class id 15 is ``cat`` — this module
is deliberately independent of which candidate task 1.3 eventually picks,
since the filtering step is identical regardless of detector architecture.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

#: Standard COCO 80-class taxonomy index for "cat" (0-indexed, no background
#: class) — consistent across Ultralytics YOLOv5/v8 exports and most other
#: COCO-pretrained detectors.
COCO_CAT_CLASS_ID = 15


@dataclass(frozen=True)
class Detection:
    """One raw detector output, before any cat-specific filtering.

    ``bbox`` is ``(x_min, y_min, x_max, y_max)``, normalized to [0, 1] against
    the input frame's width/height — matches the ``bbox_norm`` convention
    already used by ``vision_detection`` events (PEN-169).
    """

    class_id: int
    confidence: float
    bbox: Tuple[float, float, float, float]


def filter_to_cat(detections: List[Detection]) -> List[Detection]:
    """Return only the detections classified as ``cat`` (COCO class 15).

    Order is preserved; non-cat detections are dropped entirely rather than
    relabeled, since V1 has no use for other COCO classes (per proposal.md's
    "recognition of non-cat animals/objects" being out of scope for this
    change).
    """
    return [d for d in detections if d.class_id == COCO_CAT_CLASS_ID]
