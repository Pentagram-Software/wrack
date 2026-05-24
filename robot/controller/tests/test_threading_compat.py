"""Unit tests for threading_compat module."""

import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading_compat


class TestCreateLock(unittest.TestCase):
    def test_create_lock_is_usable_as_context_manager(self):
        lock = threading_compat.create_lock()
        with lock:
            pass

    def test_create_lock_uses_threading_lock_when_available(self):
        sentinel = object()

        with patch.object(threading_compat.threading, "Lock", return_value=sentinel, create=True):
            self.assertIs(threading_compat.create_lock(), sentinel)

    def test_create_lock_falls_back_to_thread_allocate_lock(self):
        fake_lock = object()
        fake_thread = type("FakeThread", (), {"allocate_lock": staticmethod(lambda: fake_lock)})()

        with patch.object(threading_compat.threading, "Lock", None, create=True):
            with patch.dict(sys.modules, {"_thread": fake_thread}):
                self.assertIs(threading_compat.create_lock(), fake_lock)

    def test_create_lock_falls_back_to_noop_when_no_primitives(self):
        with patch.object(threading_compat.threading, "Lock", None, create=True):
            with patch.dict(sys.modules, {"_thread": type("FakeThread", (), {})()}):
                lock = threading_compat.create_lock()
                self.assertIsInstance(lock, threading_compat._NoOpLock)


if __name__ == "__main__":
    unittest.main()
