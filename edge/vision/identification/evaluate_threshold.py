#!/usr/bin/env python3
"""First-pass identity confidence threshold sanity check (PEN-193, task 6.8).

**Explicitly provisional** — see `design.md`'s open question "how to
validate/tune the identity confidence threshold given the small,
hard-to-split enrollment set". This session had no access to real cat
photos, so this tool is written but not run; task 6.8 stays unchecked until
you run it against real held-out photos.

Usage::

    # held-out/ must have the same one-subfolder-per-cat layout as enroll.py's
    # --photos-dir, but with DIFFERENT photos than went into prototypes.json
    # (e.g. hold back 3-5 photos per cat before enrolling the rest).
    python3 evaluate_threshold.py --model mobilenet_v3_small_embed.onnx \\
        --prototypes prototypes.json --held-out-dir held-out/

Prints a per-photo identification result and a threshold sweep table (how
identification accuracy on the held-out set changes as the threshold moves)
to help pick a starting value for ``CatIdentifier(..., confidence_threshold=)``.
Accuracy here only reflects "does the identifier correctly pick this cat
among the *enrolled* cats" — it says nothing about the `unknown` fallback's
real-world false-positive rate, since there's no confirmed source of
"known unknown" (unfamiliar cat) photos to test against (same open question
`design.md` calls out).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from identification.embeddings import EmbeddingBackbone  # noqa: E402
from identification.enroll import _discover_photo_paths, _load_image, load_prototypes  # noqa: E402
from identification.identifier import CatIdentifier  # noqa: E402

_THRESHOLD_SWEEP = [round(0.1 * i, 1) for i in range(1, 10)]  # 0.1 .. 0.9


def evaluate(
    backbone: EmbeddingBackbone,
    prototypes: Dict[str, "object"],
    held_out_dir: Path,
) -> List[Tuple[str, str, float]]:
    """Return ``(true_identity, predicted_identity, confidence)`` for every
    held-out photo, using the identifier's raw predicted identity (not
    ``final_identity``) so the threshold sweep can be computed afterward."""
    identifier = CatIdentifier(prototypes, confidence_threshold=0.0)  # threshold applied later
    results = []
    for cat_dir in sorted(p for p in held_out_dir.iterdir() if p.is_dir()):
        for photo_path in _discover_photo_paths(cat_dir):
            embedding = backbone.embed(_load_image(photo_path))
            result = identifier.identify(embedding)
            results.append((cat_dir.name, result.predicted_identity, result.identification_confidence))
    return results


def threshold_sweep(results: List[Tuple[str, str, float]]) -> Dict[float, float]:
    """For each candidate threshold, what fraction of held-out photos would
    get a correct final_identity (predicted == true AND confidence >= threshold)?
    Note this counts "fell back to unknown" as incorrect, since there's no
    known-unknown data to say otherwise here — see module docstring."""
    accuracy_by_threshold = {}
    for threshold in _THRESHOLD_SWEEP:
        correct = sum(
            1 for true_identity, predicted, confidence in results
            if predicted == true_identity and confidence >= threshold
        )
        accuracy_by_threshold[threshold] = correct / len(results) if results else 0.0
    return accuracy_by_threshold


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Path to the exported embedding backbone ONNX model")
    parser.add_argument("--prototypes", required=True, help="Path to prototypes.json (from enroll.py)")
    parser.add_argument("--held-out-dir", required=True, help="Directory with one subfolder per cat, held out from enrollment")
    args = parser.parse_args()

    backbone = EmbeddingBackbone(args.model)
    prototypes = load_prototypes(args.prototypes)
    results = evaluate(backbone, prototypes, Path(args.held_out_dir))

    if not results:
        print("No held-out photos found under {}".format(args.held_out_dir))
        return

    print("Per-photo results:")
    for true_identity, predicted, confidence in results:
        mark = "OK" if predicted == true_identity else "MISMATCH"
        print("  {:>10} -> predicted {:>10} (confidence {:.3f})  {}".format(
            true_identity, predicted, confidence, mark
        ))

    print("\nThreshold sweep (accuracy = predicted==true AND confidence >= threshold):")
    for threshold, accuracy in threshold_sweep(results).items():
        print("  threshold={:.1f}  accuracy={:.1%}".format(threshold, accuracy))


if __name__ == "__main__":
    main()
