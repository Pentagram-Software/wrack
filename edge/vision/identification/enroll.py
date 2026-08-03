#!/usr/bin/env python3
"""Cat enrollment tool (PEN-193, task 6.3): reference photos -> an averaged
prototype embedding per cat.

Library functions (:func:`enroll_cat`, :func:`save_prototypes`,
:func:`load_prototypes`) are usable standalone; ``main()`` is the CLI for
task 6.4 — **run this on real iPhone photos of Ryfka, Chaja, and Lea** once
an embedding backbone (task 6.1/6.2) is exported to ONNX, since this session
has no access to those photos::

    python3 enroll.py --model mobilenet_v3_small_embed.onnx \\
        --photos-dir photos/ --output prototypes.json

``photos/`` must contain one subfolder per cat (``photos/ryfka/``,
``photos/chaja/``, ``photos/lea/``), each with that cat's 15-50 reference
photos (jpg/jpeg/png).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from identification.embeddings import EmbeddingBackbone, l2_normalize  # noqa: E402

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")


def enroll_cat(name: str, photo_paths: List[str], backbone: EmbeddingBackbone) -> np.ndarray:
    """Average the L2-normalized embeddings of *photo_paths* into one
    L2-normalized prototype vector for cat *name*.

    Raises ``ValueError`` if *photo_paths* is empty — a cat can't be
    enrolled from zero reference photos.
    """
    if not photo_paths:
        raise ValueError("enroll_cat requires at least one reference photo for {!r}".format(name))

    embeddings = [backbone.embed(_load_image(path)) for path in photo_paths]
    averaged = np.mean(embeddings, axis=0)
    return l2_normalize(averaged)


def _load_image(path: str) -> np.ndarray:
    import cv2

    image = cv2.imread(path)
    if image is None:
        raise ValueError("could not read image: {}".format(path))
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def save_prototypes(path: str, prototypes: Dict[str, np.ndarray]) -> None:
    """Write *prototypes* (name -> vector) to *path* as JSON."""
    serializable = {name: vector.tolist() for name, vector in prototypes.items()}
    Path(path).write_text(json.dumps(serializable))


def load_prototypes(path: str) -> Dict[str, np.ndarray]:
    """Load prototypes previously written by :func:`save_prototypes`."""
    raw = json.loads(Path(path).read_text())
    return {name: np.array(vector, dtype=np.float32) for name, vector in raw.items()}


def _discover_photo_paths(cat_dir: Path) -> List[str]:
    return [
        str(p) for p in sorted(cat_dir.iterdir()) if p.suffix.lower() in _IMAGE_SUFFIXES
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Path to the exported embedding backbone ONNX model")
    parser.add_argument(
        "--photos-dir",
        required=True,
        help="Directory with one subfolder per cat, e.g. photos/ryfka/*.jpg",
    )
    parser.add_argument("--output", required=True, help="Where to write the prototypes JSON")
    args = parser.parse_args()

    backbone = EmbeddingBackbone(args.model)
    photos_root = Path(args.photos_dir)

    prototypes: Dict[str, np.ndarray] = {}
    for cat_dir in sorted(p for p in photos_root.iterdir() if p.is_dir()):
        photo_paths = _discover_photo_paths(cat_dir)
        if not photo_paths:
            print("skipping {} - no photos found".format(cat_dir.name))
            continue
        print("enrolling {} from {} photos".format(cat_dir.name, len(photo_paths)))
        prototypes[cat_dir.name] = enroll_cat(cat_dir.name, photo_paths, backbone)

    save_prototypes(args.output, prototypes)
    print("wrote prototypes for {} cats to {}".format(len(prototypes), args.output))


if __name__ == "__main__":
    main()
