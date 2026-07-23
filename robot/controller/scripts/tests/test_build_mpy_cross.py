#!/usr/bin/env python3
"""
Unit tests for build_mpy_cross.py.

These tests never touch the network or invoke a real compiler -- subprocess
calls (git/make) and the filesystem are mocked so the tests run anywhere,
including CI environments without build tooling.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_mpy_cross


class TestPaths(unittest.TestCase):
    def test_micropython_src_dir(self):
        cache_dir = Path("/tmp/cache")
        self.assertEqual(
            build_mpy_cross.micropython_src_dir(cache_dir),
            Path("/tmp/cache/micropython"),
        )

    def test_mpy_cross_binary_path(self):
        cache_dir = Path("/tmp/cache")
        self.assertEqual(
            build_mpy_cross.mpy_cross_binary_path(cache_dir),
            Path("/tmp/cache/micropython/mpy-cross/build/mpy-cross"),
        )

    def test_default_cache_dir_is_outside_robot_controller(self):
        cache_dir = build_mpy_cross.default_cache_dir()
        repo_root = build_mpy_cross.repo_root()
        self.assertEqual(cache_dir.parent, repo_root)
        self.assertNotIn("robot", cache_dir.parts)


class TestIsBinaryUsable(unittest.TestCase):
    def test_missing_file_is_not_usable(self):
        self.assertFalse(build_mpy_cross.is_binary_usable(Path("/no/such/binary")))

    @patch("build_mpy_cross.subprocess.run")
    @patch("build_mpy_cross.os.access", return_value=True)
    def test_existing_executable_that_runs_is_usable(self, mock_access, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        with patch.object(Path, "is_file", return_value=True):
            self.assertTrue(build_mpy_cross.is_binary_usable(Path("/fake/mpy-cross")))

    @patch("build_mpy_cross.subprocess.run")
    @patch("build_mpy_cross.os.access", return_value=True)
    def test_existing_executable_that_errors_is_not_usable(self, mock_access, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        with patch.object(Path, "is_file", return_value=True):
            self.assertFalse(build_mpy_cross.is_binary_usable(Path("/fake/mpy-cross")))

    @patch("build_mpy_cross.subprocess.run", side_effect=OSError("not executable"))
    @patch("build_mpy_cross.os.access", return_value=True)
    def test_binary_that_cannot_run_is_not_usable(self, mock_access, mock_run):
        with patch.object(Path, "is_file", return_value=True):
            self.assertFalse(build_mpy_cross.is_binary_usable(Path("/fake/mpy-cross")))


class TestCloneSource(unittest.TestCase):
    @patch("build_mpy_cross.subprocess.run")
    def test_skips_clone_when_source_already_exists(self, mock_run, tmp_path=None):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            (cache_dir / "micropython").mkdir()
            result = build_mpy_cross.clone_source(cache_dir)
            mock_run.assert_not_called()
            self.assertEqual(result, cache_dir / "micropython")

    @patch("build_mpy_cross.subprocess.run")
    def test_clones_pinned_tag_when_source_missing(self, mock_run):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            build_mpy_cross.clone_source(cache_dir, tag="v1.11")

            mock_run.assert_called_once()
            called_args = mock_run.call_args[0][0]
            self.assertIn("git", called_args)
            self.assertIn("clone", called_args)
            self.assertIn("--branch", called_args)
            self.assertIn("v1.11", called_args)
            self.assertIn(build_mpy_cross.MICROPYTHON_REPO_URL, called_args)


class TestBuildMpyCross(unittest.TestCase):
    @patch("build_mpy_cross.subprocess.run")
    def test_invokes_make_in_mpy_cross_subdir(self, mock_run):
        src_dir = Path("/tmp/cache/micropython")
        result = build_mpy_cross.build_mpy_cross(src_dir, jobs=4)

        mock_run.assert_called_once()
        called_args = mock_run.call_args[0][0]
        self.assertEqual(called_args[0], "make")
        self.assertIn(str(src_dir / "mpy-cross"), called_args)
        self.assertIn("-j4", called_args)
        # Must be passed as CFLAGS_MOD (not CFLAGS_EXTRA/COPT) -- see the
        # comment on EXTRA_CFLAGS_VAR for why those two are silently ignored.
        self.assertIn(
            f"{build_mpy_cross.EXTRA_CFLAGS_VAR}={build_mpy_cross.EXTRA_CFLAGS}",
            called_args,
        )
        self.assertEqual(result, src_dir / "mpy-cross" / "build" / "mpy-cross")

    @patch("build_mpy_cross.subprocess.run")
    def test_propagates_build_failures(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, ["make"])
        with self.assertRaises(subprocess.CalledProcessError):
            build_mpy_cross.build_mpy_cross(Path("/tmp/cache/micropython"))


class TestEnsureMpyCross(unittest.TestCase):
    @patch("build_mpy_cross.is_binary_usable", return_value=True)
    @patch("build_mpy_cross.clone_source")
    @patch("build_mpy_cross.build_mpy_cross")
    def test_reuses_cached_binary_without_rebuilding(
        self, mock_build, mock_clone, mock_usable
    ):
        cache_dir = Path("/tmp/cache")
        result = build_mpy_cross.ensure_mpy_cross(cache_dir=cache_dir)

        mock_clone.assert_not_called()
        mock_build.assert_not_called()
        self.assertEqual(result, build_mpy_cross.mpy_cross_binary_path(cache_dir))

    @patch("build_mpy_cross.is_binary_usable", return_value=True)
    @patch("build_mpy_cross.clone_source")
    @patch("build_mpy_cross.build_mpy_cross")
    def test_force_rebuild_ignores_cache(self, mock_build, mock_clone, mock_usable):
        cache_dir = Path("/tmp/cache")
        build_mpy_cross.ensure_mpy_cross(cache_dir=cache_dir, force_rebuild=True)

        mock_clone.assert_called_once()
        mock_build.assert_called_once()

    @patch("build_mpy_cross.is_binary_usable", side_effect=[False, True])
    @patch("build_mpy_cross.clone_source")
    @patch("build_mpy_cross.build_mpy_cross")
    def test_builds_when_no_cached_binary(self, mock_build, mock_clone, mock_usable):
        cache_dir = Path("/tmp/cache")
        mock_clone.return_value = cache_dir / "micropython"

        build_mpy_cross.ensure_mpy_cross(cache_dir=cache_dir)

        mock_clone.assert_called_once_with(cache_dir, verbose=False)
        mock_build.assert_called_once()

    @patch("build_mpy_cross.is_binary_usable", return_value=False)
    @patch("build_mpy_cross.clone_source")
    @patch("build_mpy_cross.build_mpy_cross")
    def test_raises_if_build_did_not_produce_usable_binary(
        self, mock_build, mock_clone, mock_usable
    ):
        with self.assertRaises(RuntimeError):
            build_mpy_cross.ensure_mpy_cross(cache_dir=Path("/tmp/cache"))


class TestCheckTooling(unittest.TestCase):
    @patch("build_mpy_cross.shutil.which", return_value=None)
    def test_reports_missing_git(self, mock_which):
        error = build_mpy_cross._check_tooling()
        self.assertIsNotNone(error)
        self.assertIn("git", error)

    @patch("build_mpy_cross.shutil.which", side_effect=lambda name: None if name == "make" else "/usr/bin/git")
    def test_reports_missing_make(self, mock_which):
        error = build_mpy_cross._check_tooling()
        self.assertIsNotNone(error)
        self.assertIn("make", error)

    @patch("build_mpy_cross.shutil.which", return_value="/usr/bin/tool")
    def test_no_error_when_tooling_present(self, mock_which):
        self.assertIsNone(build_mpy_cross._check_tooling())


if __name__ == "__main__":
    unittest.main()
