"""Unit tests for identification/enroll.py (PEN-262, task 6.3)."""

import numpy as np
import pytest

import identification.enroll as enroll_module
from identification.enroll import enroll_cat, load_prototypes, main, save_prototypes


class _FakeBackbone:
    """Returns a fixed-but-distinguishable embedding per mean pixel value,
    so averaging behavior is checkable without a real ONNX model."""

    def embed(self, crop: np.ndarray) -> np.ndarray:
        brightness = float(crop.mean()) / 255.0
        vector = np.array([brightness, 1.0 - brightness], dtype=np.float32)
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector


def _write_image(path, value):
    import cv2

    image = np.full((16, 16, 3), value, dtype=np.uint8)
    cv2.imwrite(str(path), image)


class TestEnrollCat:
    def test_raises_on_empty_photo_list(self):
        with pytest.raises(ValueError):
            enroll_cat("ryfka", [], _FakeBackbone())

    def test_returns_unit_length_prototype(self, tmp_path):
        photo = tmp_path / "photo1.png"
        _write_image(photo, 128)

        prototype = enroll_cat("ryfka", [str(photo)], _FakeBackbone())

        assert np.linalg.norm(prototype) == pytest.approx(1.0)

    def test_averages_multiple_photos(self, tmp_path):
        dark = tmp_path / "dark.png"
        light = tmp_path / "light.png"
        _write_image(dark, 0)
        _write_image(light, 255)

        prototype = enroll_cat("ryfka", [str(dark), str(light)], _FakeBackbone())
        single_dark = enroll_cat("ryfka", [str(dark)], _FakeBackbone())

        # Averaging a dark and a light photo must differ from enrolling the
        # dark photo alone — otherwise the average isn't actually blending.
        assert not np.allclose(prototype, single_dark)

    def test_raises_on_unreadable_image(self, tmp_path):
        bogus = tmp_path / "not-an-image.png"
        bogus.write_text("not actually image bytes")
        with pytest.raises(ValueError):
            enroll_cat("ryfka", [str(bogus)], _FakeBackbone())


class TestSaveLoadPrototypesRoundTrip:
    def test_round_trip_preserves_values(self, tmp_path):
        prototypes = {
            "ryfka": np.array([0.6, 0.8], dtype=np.float32),
            "chaja": np.array([1.0, 0.0], dtype=np.float32),
        }
        output_path = tmp_path / "prototypes.json"

        save_prototypes(str(output_path), prototypes)
        loaded = load_prototypes(str(output_path))

        assert set(loaded.keys()) == {"ryfka", "chaja"}
        np.testing.assert_allclose(loaded["ryfka"], prototypes["ryfka"], atol=1e-6)
        np.testing.assert_allclose(loaded["chaja"], prototypes["chaja"], atol=1e-6)


class TestMainCli:
    def test_enrolls_each_cat_subfolder_and_skips_empty_ones(self, tmp_path, monkeypatch, capsys):
        photos_dir = tmp_path / "photos"
        (photos_dir / "ryfka").mkdir(parents=True)
        (photos_dir / "chaja").mkdir(parents=True)
        (photos_dir / "empty_cat").mkdir(parents=True)
        _write_image(photos_dir / "ryfka" / "1.png", 50)
        _write_image(photos_dir / "ryfka" / "2.png", 60)
        _write_image(photos_dir / "chaja" / "1.png", 200)

        output_path = tmp_path / "prototypes.json"
        monkeypatch.setattr(enroll_module, "EmbeddingBackbone", lambda model_path: _FakeBackbone())
        monkeypatch.setattr(
            "sys.argv",
            [
                "enroll.py",
                "--model",
                "unused.onnx",
                "--photos-dir",
                str(photos_dir),
                "--output",
                str(output_path),
            ],
        )

        main()

        loaded = load_prototypes(str(output_path))
        assert set(loaded.keys()) == {"ryfka", "chaja"}
        captured = capsys.readouterr()
        assert "empty_cat" in captured.out
