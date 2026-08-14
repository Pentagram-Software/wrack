"""Guard against reintroducing thread kwargs MicroPython rejects.

Pybricks MicroPython's ``Thread()`` accepts only ``target``/``args``;
``daemon`` and ``name`` raise ``TypeError``. That exception propagates out
of ``EventHandler.trigger()`` and kills the calling worker thread for the
rest of the session -- for the PS4 reader, the "READ LOOP IS DEAD" case.

This cannot be caught by running the code on CPython, where the kwargs are
valid, nor by ``make check-mpy``, which is a syntax-only check. PEN-188
fixed one instance; this keeps the rest from coming back.
"""

import ast
import os
import unittest


CONTROLLER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REJECTED_KWARGS = ("daemon", "name")

# Directories that never ship to the EV3.
SKIP_DIRS = {".venv", "tests", "scripts", "__pycache__", "examples", "docs"}


def _shipped_python_files():
    for dirpath, dirnames, filenames in os.walk(CONTROLLER_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            if filename.endswith(".py"):
                yield os.path.join(dirpath, filename)


def _is_thread_construction(node):
    """Match Thread(...), threading.Thread(...), and Thread.__init__(...)."""
    func = node.func
    if isinstance(func, ast.Attribute):
        if func.attr == "Thread":
            return True
        # threading.Thread.__init__(self, ...)
        if func.attr == "__init__" and isinstance(func.value, ast.Attribute):
            return func.value.attr == "Thread"
        return False
    return isinstance(func, ast.Name) and func.id == "Thread"


def _offending_calls(path):
    with open(path) as handle:
        tree = ast.parse(handle.read(), path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_thread_construction(node):
            continue
        for keyword in node.keywords:
            if keyword.arg in REJECTED_KWARGS:
                yield (
                    os.path.relpath(path, CONTROLLER_ROOT),
                    node.lineno,
                    keyword.arg,
                )


class TestThreadKwargs(unittest.TestCase):

    def test_no_shipped_file_passes_daemon_or_name_to_thread(self):
        offenders = [
            "{}:{} passes {}=".format(path, lineno, kwarg)
            for source in _shipped_python_files()
            for path, lineno, kwarg in _offending_calls(source)
        ]

        self.assertEqual(
            offenders,
            [],
            "Pybricks MicroPython's Thread() rejects these kwargs with "
            "TypeError, killing the calling thread:\n  "
            + "\n  ".join(offenders),
        )

    def test_the_check_actually_detects_an_offender(self):
        """A guard that cannot fail is not a guard."""
        tree = ast.parse("threading.Thread(target=f, daemon=True)")
        call = tree.body[0].value

        self.assertTrue(_is_thread_construction(call))
        self.assertEqual(
            [kw.arg for kw in call.keywords if kw.arg in REJECTED_KWARGS],
            ["daemon"],
        )

    def test_the_check_covers_the_thread_subclass_form(self):
        tree = ast.parse("threading.Thread.__init__(self, daemon=True)")

        self.assertTrue(_is_thread_construction(tree.body[0].value))

    def test_target_and_args_are_allowed(self):
        tree = ast.parse("threading.Thread(target=f, args=(1,))")
        call = tree.body[0].value

        self.assertEqual(
            [kw.arg for kw in call.keywords if kw.arg in REJECTED_KWARGS], []
        )


if __name__ == "__main__":
    unittest.main()
