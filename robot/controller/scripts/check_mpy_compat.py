#!/usr/bin/env python3
"""
Check that every file deployed to the EV3 actually compiles under MicroPython.

The pytest suite runs on CPython and cannot catch MicroPython-only syntax
incompatibilities (see robot/controller's MicroPython compatibility checklist
in the repo root CLAUDE.md). This script closes part of that gap by running
mpy-cross -- the real MicroPython cross-compiler, pinned to the exact version
the EV3's frozen Pybricks firmware uses (see build_mpy_cross.py) -- against
every file that actually gets shipped to the brick.

If a file compiles, it is syntactically valid MicroPython. If it fails,
mpy-cross reports the exact file and line, which is much faster feedback than
deploying to the EV3 and reading a crash log.

Scope / limitations
--------------------
This only catches *syntax*-level incompatibilities (mpy-cross parses and
compiles, it never executes). It will NOT catch:
  - Missing/partial stdlib modules or attributes (e.g. `datetime`, `re`,
    `uuid.uuid4`) -- those only fail at import/runtime.
  - The bare `format()` builtin being unavailable -- also a runtime-only gap.
  - Anything else that is valid MicroPython grammar but behaves differently
    at runtime.
See robot/controller's MicroPython compatibility checklist for the full list
of known bug classes and how to guard against the ones this script can't see.

Usage:
    python3 scripts/check_mpy_compat.py
    python3 scripts/check_mpy_compat.py --verbose
    python3 scripts/check_mpy_compat.py --mpy-cross /path/to/mpy-cross
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import build_mpy_cross
from deploy_ev3 import get_files_to_deploy


def find_files_to_check(source_dir: Path) -> List[Path]:
    """Return .py files that actually get deployed to the EV3.

    Reuses deploy_ev3.get_files_to_deploy() as the single source of truth for
    "what ships to the brick", so this check never drifts from what
    `make deploy-robot` actually sends (and never lints CPython-only files
    such as tests/, scripts/, or setup.py helpers).
    """
    rel_paths = get_files_to_deploy(str(source_dir))
    return [source_dir / rel for rel in rel_paths if rel.endswith(".py")]


def compile_file(mpy_cross: Path, file_path: Path) -> Optional[str]:
    """Try to compile file_path with mpy_cross. Return None on success, else an error message."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / (file_path.stem + ".mpy")
        try:
            result = subprocess.run(
                [str(mpy_cross), str(file_path), "-o", str(out_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except OSError as exc:
            return f"failed to run mpy-cross: {exc}"
        except subprocess.TimeoutExpired:
            return "mpy-cross timed out"

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip()
            return message or f"mpy-cross exited with status {result.returncode}"
    return None


def check_files(
    mpy_cross: Path, source_dir: Path, verbose: bool = False
) -> List[Tuple[str, str]]:
    """Compile every deployed .py file. Return a list of (relative_path, error) failures."""
    failures: List[Tuple[str, str]] = []
    for file_path in find_files_to_check(source_dir):
        rel_path = str(file_path.relative_to(source_dir))
        if verbose:
            print(f"Checking {rel_path} ...")
        error = compile_file(mpy_cross, file_path)
        if error is not None:
            failures.append((rel_path, error))
    return failures


def resolve_mpy_cross_path(explicit: Optional[str]) -> Path:
    """Resolve the mpy-cross binary to use, in priority order:

    1. --mpy-cross CLI argument
    2. MPY_CROSS_BIN environment variable
    3. The default build cache (see build_mpy_cross.py)
    4. `mpy-cross` on PATH
    """
    if explicit:
        return Path(explicit)

    env_path = os.environ.get("MPY_CROSS_BIN")
    if env_path:
        return Path(env_path)

    cached = build_mpy_cross.mpy_cross_binary_path(build_mpy_cross.default_cache_dir())
    if build_mpy_cross.is_binary_usable(cached):
        return cached

    which = shutil.which("mpy-cross")
    if which:
        return Path(which)

    raise FileNotFoundError(
        "mpy-cross binary not found. Run 'python3 scripts/build_mpy_cross.py' first "
        "(or 'make check-mpy' from the repo root to build + check in one step)."
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="robot/controller directory to check (default: auto-detected)",
    )
    parser.add_argument(
        "--mpy-cross",
        default=None,
        help="Path to the mpy-cross binary (default: auto-detected, see resolve_mpy_cross_path)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    try:
        mpy_cross = resolve_mpy_cross_path(args.mpy_cross)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not build_mpy_cross.is_binary_usable(mpy_cross):
        print(f"error: mpy-cross at {mpy_cross} is not usable", file=sys.stderr)
        return 2

    files = find_files_to_check(args.source_dir)
    if args.verbose:
        print(f"Checking {len(files)} file(s) against {mpy_cross} ...")

    failures = check_files(mpy_cross, args.source_dir, verbose=args.verbose)

    if failures:
        print(
            f"\nMicroPython compatibility check FAILED for {len(failures)} file(s):\n",
            file=sys.stderr,
        )
        for rel_path, error in failures:
            print(f"  {rel_path}:", file=sys.stderr)
            for line in error.splitlines():
                print(f"    {line}", file=sys.stderr)
        return 1

    print(f"MicroPython compatibility check passed ({len(files)} file(s) checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
