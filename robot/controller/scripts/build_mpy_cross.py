#!/usr/bin/env python3
"""
Build (or reuse a cached build of) the mpy-cross MicroPython cross-compiler,
pinned to the exact MicroPython version used by the EV3's Pybricks firmware.

Why build from source instead of `pip install mpy-cross-*`
------------------------------------------------------------
PyPI's mpy-cross packages (mpy-cross-v5 .. mpy-cross-v6.3, mpy-cross-multi) are
all built from *current* upstream MicroPython compiler source; they only differ
in which .mpy bytecode ABI they emit. They do not reproduce the actual grammar
accepted by the EV3.

The EV3 runs Pybricks "2.0" (the last release with ev3dev/EV3 support -- ev3dev
support was dropped entirely in pybricks-micropython v4.0.0). That release is
permanently frozen and pins upstream MicroPython at exactly `v1.11` (see the
`micropython-tag` file in the pybricks-micropython v2.0.0 release, which reads
"v1.11+pybricks2.0.0"). Pybricks' EV3-specific patches live in `bricks/ev3dev/`
and the `pybricks` module -- they do not touch the core `py/compile.c`,
`py/parse.c`, or `py/grammar.h` files that decide what is/isn't valid syntax.
So vanilla MicroPython v1.11's own mpy-cross is a faithful stand-in for the
EV3's actual compiler, without needing Pybricks' own (Docker-based) firmware
build.

This matters in practice: MicroPython v1.11's grammar has no "annassign" rule
at all (PEP 526 variable annotations, e.g. `x: int = 1`, were added upstream
well after v1.11). That's exactly the bug class that took down telemetry in
production (see commit 5842035, "remove annotated attribute assignment
breaking MicroPython") -- and it's a class of bug that current PyPI mpy-cross
wheels no longer catch, because upstream MicroPython now parses (and silently
ignores) annotations on any assignment target. Pinning to v1.11 is what makes
this check catch that bug class again.

Usage:
    python3 scripts/build_mpy_cross.py
    python3 scripts/build_mpy_cross.py --force
    python3 scripts/build_mpy_cross.py --cache-dir /path/to/cache --verbose
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Upstream MicroPython tag pinned by the frozen Pybricks EV3 "2.0" firmware.
# Do not bump this without confirming the EV3 firmware itself has moved --
# see the module docstring above.
MICROPYTHON_REPO_URL = "https://github.com/micropython/micropython.git"
MICROPYTHON_TAG = "v1.11"

# mpy-cross is a MicroPython 1.11-vintage host build. Modern compilers (e.g.
# GCC 12+ on current ubuntu-latest runners) promote warning classes this old
# code triggers (e.g. -Wdangling-pointer) to hard errors by default, and a
# blanket `-Wno-error` does not un-promote a specific `-Werror=X` class -- so
# just suppress all warnings outright rather than chase each new compiler's
# stricter defaults one flag at a time.
#
# This must be passed as CFLAGS_MOD, not CFLAGS_EXTRA or COPT: mpy-cross's own
# Makefile has a `override undefine CFLAGS_EXTRA` / `override undefine COPT`
# guard at the top (to protect against a *calling* Makefile leaking those
# vars in), which silently wins over anything we set via env var or
# command line for those two names specifically. CFLAGS_MOD isn't touched by
# that guard and is threaded into CFLAGS, so it's the one override that
# actually survives.
EXTRA_CFLAGS_VAR = "CFLAGS_MOD"
EXTRA_CFLAGS = "-w"


def repo_root() -> Path:
    """Return the wrack monorepo root (this file lives in robot/controller/scripts/)."""
    return Path(__file__).resolve().parents[3]


def default_cache_dir() -> Path:
    """Default location for the cloned MicroPython source + built binary.

    Deliberately outside robot/controller/ so it is never picked up by
    deploy_ev3.get_files_to_deploy() (i.e. never accidentally shipped to the
    EV3 or fed into check_mpy_compat.py's own file list).
    """
    return repo_root() / ".mpy-cross-cache"


def micropython_src_dir(cache_dir: Path) -> Path:
    return cache_dir / "micropython"


def mpy_cross_binary_path(cache_dir: Path) -> Path:
    return micropython_src_dir(cache_dir) / "mpy-cross" / "build" / "mpy-cross"


def is_binary_usable(binary_path: Path, verbose: bool = False) -> bool:
    """Check whether a previously built mpy-cross binary still runs."""
    if not binary_path.is_file() or not os.access(binary_path, os.X_OK):
        if verbose:
            print(f"{binary_path} does not exist or is not executable", file=sys.stderr)
        return False
    try:
        result = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        if verbose:
            print(f"running {binary_path} --version raised {exc!r}", file=sys.stderr)
        return False
    if result.returncode != 0 and verbose:
        print(
            f"{binary_path} --version exited {result.returncode}\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}",
            file=sys.stderr,
        )
    return result.returncode == 0


def clone_source(
    cache_dir: Path, tag: str = MICROPYTHON_TAG, verbose: bool = False
) -> Path:
    """Shallow-clone MicroPython at the pinned tag into cache_dir. Idempotent."""
    src_dir = micropython_src_dir(cache_dir)
    if src_dir.exists():
        if verbose:
            print(f"Using existing clone at {src_dir}")
        return src_dir

    cache_dir.mkdir(parents=True, exist_ok=True)
    if verbose:
        print(f"Cloning {MICROPYTHON_REPO_URL} @ {tag} into {src_dir} ...")
    subprocess.run(
        [
            "git",
            "clone",
            "--branch",
            tag,
            "--depth",
            "1",
            MICROPYTHON_REPO_URL,
            str(src_dir),
        ],
        check=True,
    )
    return src_dir


def build_mpy_cross(src_dir: Path, jobs: Optional[int] = None, verbose: bool = False) -> Path:
    """Run `make` in <src_dir>/mpy-cross. Raises subprocess.CalledProcessError on failure."""
    mpy_cross_dir = src_dir / "mpy-cross"
    jobs = jobs or os.cpu_count() or 1
    if verbose:
        print(f"Building mpy-cross in {mpy_cross_dir} (jobs={jobs}) ...")
    subprocess.run(
        [
            "make",
            "-C",
            str(mpy_cross_dir),
            f"-j{jobs}",
            f"{EXTRA_CFLAGS_VAR}={EXTRA_CFLAGS}",
        ],
        check=True,
    )
    return mpy_cross_dir / "build" / "mpy-cross"


def ensure_mpy_cross(
    cache_dir: Optional[Path] = None,
    force_rebuild: bool = False,
    jobs: Optional[int] = None,
    verbose: bool = False,
) -> Path:
    """Return a path to a working mpy-cross binary, building it if necessary."""
    cache_dir = cache_dir or default_cache_dir()
    binary_path = mpy_cross_binary_path(cache_dir)

    if not force_rebuild and is_binary_usable(binary_path, verbose=verbose):
        if verbose:
            print(f"Reusing cached mpy-cross at {binary_path}")
        return binary_path

    src_dir = clone_source(cache_dir, verbose=verbose)
    build_mpy_cross(src_dir, jobs=jobs, verbose=verbose)

    if not is_binary_usable(binary_path, verbose=True):
        raise RuntimeError(
            f"mpy-cross build finished but binary at {binary_path} is not usable"
        )
    return binary_path


def _check_tooling() -> Optional[str]:
    """Return an error message if required build tools are missing, else None."""
    if shutil.which("git") is None:
        return "git is required to fetch MicroPython source but was not found on PATH."
    if shutil.which("make") is None:
        return (
            "make is required to build mpy-cross but was not found on PATH. "
            "Install build-essential (Linux) or Xcode command line tools (macOS)."
        )
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Directory to clone/build MicroPython into (default: <repo>/.mpy-cross-cache)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even if a cached binary already works",
    )
    parser.add_argument("--jobs", "-j", type=int, default=None, help="Parallel make jobs")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    # stdout defaults to block-buffered when not a tty (e.g. piped into a CI
    # log), which interleaves our own prints out of order relative to the
    # subprocess (git/make) output that writes directly to the inherited fd.
    # Line-buffer so `--verbose` output stays in chronological order in logs.
    sys.stdout.reconfigure(line_buffering=True)

    tooling_error = _check_tooling()
    if tooling_error:
        print(f"error: {tooling_error}", file=sys.stderr)
        return 1

    try:
        binary_path = ensure_mpy_cross(
            cache_dir=args.cache_dir,
            force_rebuild=args.force,
            jobs=args.jobs,
            verbose=args.verbose,
        )
    except subprocess.CalledProcessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(str(binary_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
