"""Unit tests for detection/coco.py (COCO cat-class filtering, PEN-238)."""

from detection.coco import COCO_CAT_CLASS_ID, Detection, filter_to_cat


def _det(class_id, confidence=0.9, bbox=(0.1, 0.1, 0.5, 0.5)):
    return Detection(class_id=class_id, confidence=confidence, bbox=bbox)


class TestFilterToCat:
    def test_cat_class_id_is_15(self):
        assert COCO_CAT_CLASS_ID == 15

    def test_keeps_only_cat_detections(self):
        detections = [_det(class_id=0), _det(class_id=15), _det(class_id=16)]
        result = filter_to_cat(detections)
        assert len(result) == 1
        assert result[0].class_id == 15

    def test_empty_input_returns_empty(self):
        assert filter_to_cat([]) == []

    def test_no_cats_returns_empty(self):
        detections = [_det(class_id=0), _det(class_id=2), _det(class_id=16)]
        assert filter_to_cat(detections) == []

    def test_multiple_cats_preserved_in_order(self):
        detections = [_det(class_id=15, confidence=0.5), _det(class_id=0), _det(class_id=15, confidence=0.9)]
        result = filter_to_cat(detections)
        assert [d.confidence for d in result] == [0.5, 0.9]

    def test_non_cat_detections_dropped_not_relabeled(self):
        detections = [_det(class_id=16)]
        assert filter_to_cat(detections) == []

    def test_detection_is_frozen(self):
        d = _det(class_id=15)
        try:
            d.class_id = 0
            assert False, "Detection should be immutable"
        except AttributeError:
            pass
