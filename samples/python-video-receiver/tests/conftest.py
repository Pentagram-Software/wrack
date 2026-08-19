"""
Pytest configuration for the python-video-receiver test suite.

Adds the package root to sys.path so modules can be imported directly, and
provides the ``receiver`` shim that legacy tests expect (``receiver.main``
maps to the top-level ``main`` module).
"""

import importlib
import sys
import types
from pathlib import Path

# Make the receiver root importable without installation
RECEIVER_ROOT = Path(__file__).resolve().parents[1]
if str(RECEIVER_ROOT) not in sys.path:
    sys.path.insert(0, str(RECEIVER_ROOT))

# Create a synthetic ``receiver`` package whose ``main`` submodule points at
# the top-level ``main.py``.  This lets existing tests written as
# ``from receiver import main as receiver_main`` continue to work unchanged.
if "receiver" not in sys.modules:
    receiver_pkg = types.ModuleType("receiver")
    receiver_pkg.__path__ = [str(RECEIVER_ROOT)]  # type: ignore[assignment]
    receiver_pkg.__package__ = "receiver"
    sys.modules["receiver"] = receiver_pkg

if "receiver.main" not in sys.modules:
    main_module = importlib.import_module("main")
    sys.modules["receiver.main"] = main_module
    sys.modules["receiver"].main = main_module  # type: ignore[attr-defined]
