#!/usr/bin/env python3
"""
Unit tests for check_mpy_compat.py.

Uses a small stub "mpy-cross" script (see _write_stub_mpy_cross below) instead
of the real compiler, so these tests run without needing mpy-cross built and
without depending on real MicroPython grammar behavior.
"""

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import check_mpy_compat

FAIL_MARKER = "FAIL_MARKER"

# A tiny stand-in for mpy-cross: fails (mimicking a SyntaxError) for any
# source file containing FAIL_MARKER, succeeds otherwise. Mirrors mpy-cross's
# real CLI contract closely enough for this script's own logic to be tested:
# `<binary> <input.py> -o <output.mpy>`.
STUB_MPY_CROSS = f"""#!/usr/bin/env python3
import sys
if sys.argv[1:] == ["--version"]:
    print("stub mpy-cross v0.0.0")
    sys.exit(0)
with open(sys.argv[1]) as f:
    content = f.read()
if "{FAIL_MARKER}" in content:
    sys.stderr.write('File "%s", line 1\\nSyntaxError: invalid syntax\\n' % sys.argv[1])
    sys.exit(1)
sys.exit(0)
"""


def _write_stub_mpy_cross(directory: Path) -> Path:
    stub_path = directory / "mpy-cross"
    stub_path.write_text(STUB_MPY_CROSS)
    stub_path.chmod(stub_path.stat().st_mode | stat.S_IEXEC)
    return stub_path


def _make_fake_controller_tree(root: Path) -> None:
    """Mimic just enough of robot/controller/ for get_files_to_deploy() to work."""
    (root / "main.py").write_text("print('hello')\n")
    (root / "good_module.py").write_text("x = 1\nprint(x)\n")
    (root / "bad_module.py").write_text(f"x = 1  # {FAIL_MARKER}\n")

    tests_dir = root / "tests"
    tests_dir.mkdir()
    # Deliberately "bad" per the stub -- must NOT be checked, since tests/ is
    # excluded from deployment (and is CPython-only anyway).
    (tests_dir / "test_something.py").write_text(f"# {FAIL_MARKER}\n")


class TestFindFilesToCheck(unittest.TestCase):
    def test_includes_only_deployed_py_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_controller_tree(root)

            files = check_mpy_compat.find_files_to_check(root)
            rel_names = sorted(f.name for f in files)

            self.assertIn("main.py", rel_names)
            self.assertIn("good_module.py", rel_names)
            self.assertIn("bad_module.py", rel_names)
            self.assertNotIn("test_something.py", rel_names)


class TestCompileFile(unittest.TestCase):
    def test_returns_none_for_compilable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = _write_stub_mpy_cross(root)
            good_file = root / "good.py"
            good_file.write_text("x = 1\n")

            self.assertIsNone(check_mpy_compat.compile_file(stub, good_file))

    def test_returns_error_message_for_failing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = _write_stub_mpy_cross(root)
            bad_file = root / "bad.py"
            bad_file.write_text(f"x = 1  # {FAIL_MARKER}\n")

            error = check_mpy_compat.compile_file(stub, bad_file)
            self.assertIsNotNone(error)
            self.assertIn("SyntaxError", error)

    def test_returns_error_for_nonexistent_binary(self):
        error = check_mpy_compat.compile_file(
            Path("/no/such/mpy-cross"), Path("/no/such/file.py")
        )
        self.assertIsNotNone(error)


class TestCheckFiles(unittest.TestCase):
    def test_aggregates_failures_across_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = _write_stub_mpy_cross(root)
            _make_fake_controller_tree(root)

            failures = check_mpy_compat.check_files(stub, root)

            failed_names = {name for name, _ in failures}
            self.assertEqual(failed_names, {"bad_module.py"})

    def test_no_failures_when_all_files_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = _write_stub_mpy_cross(root)
            (root / "main.py").write_text("print('ok')\n")

            failures = check_mpy_compat.check_files(stub, root)
            self.assertEqual(failures, [])


class TestResolveMpyCrossPath(unittest.TestCase):
    def test_explicit_argument_wins(self):
        result = check_mpy_compat.resolve_mpy_cross_path("/explicit/path")
        self.assertEqual(result, Path("/explicit/path"))

    def test_falls_back_to_env_var(self):
        with patch.dict(os.environ, {"MPY_CROSS_BIN": "/from/env"}):
            result = check_mpy_compat.resolve_mpy_cross_path(None)
        self.assertEqual(result, Path("/from/env"))

    def test_falls_back_to_path_lookup(self):
        env = {k: v for k, v in os.environ.items() if k != "MPY_CROSS_BIN"}
        with patch.dict(os.environ, env, clear=True), patch(
            "check_mpy_compat.build_mpy_cross.is_binary_usable", return_value=False
        ), patch("check_mpy_compat.shutil.which", return_value="/usr/local/bin/mpy-cross"):
            result = check_mpy_compat.resolve_mpy_cross_path(None)
        self.assertEqual(result, Path("/usr/local/bin/mpy-cross"))

    def test_raises_when_nothing_found(self):
        env = {k: v for k, v in os.environ.items() if k != "MPY_CROSS_BIN"}
        with patch.dict(os.environ, env, clear=True), patch(
            "check_mpy_compat.build_mpy_cross.is_binary_usable", return_value=False
        ), patch("check_mpy_compat.shutil.which", return_value=None):
            with self.assertRaises(FileNotFoundError):
                check_mpy_compat.resolve_mpy_cross_path(None)


class TestMain(unittest.TestCase):
    def test_exit_code_zero_when_all_files_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = _write_stub_mpy_cross(root)
            (root / "main.py").write_text("print('ok')\n")

            exit_code = check_mpy_compat.main(
                ["--source-dir", str(root), "--mpy-cross", str(stub)]
            )
            self.assertEqual(exit_code, 0)

    def test_exit_code_one_when_a_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = _write_stub_mpy_cross(root)
            _make_fake_controller_tree(root)

            exit_code = check_mpy_compat.main(
                ["--source-dir", str(root), "--mpy-cross", str(stub)]
            )
            self.assertEqual(exit_code, 1)

    def test_exit_code_two_when_mpy_cross_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("print('ok')\n")

            exit_code = check_mpy_compat.main(
                ["--source-dir", str(root), "--mpy-cross", "/no/such/mpy-cross"]
            )
            self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
