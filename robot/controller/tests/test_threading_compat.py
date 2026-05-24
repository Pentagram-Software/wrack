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


class TestWaitForWorkers(unittest.TestCase):
    class FakeWorker:
        def __init__(self, stopped=False, running=None):
            self.stopped = stopped
            if running is not None:
                self.running = running

        def is_running(self):
            return self.running

    def test_worker_is_running_uses_stopped_flag(self):
        worker = self.FakeWorker(stopped=False)
        self.assertTrue(threading_compat.worker_is_running(worker))
        worker.stopped = True
        self.assertFalse(threading_compat.worker_is_running(worker))

    def test_worker_is_running_uses_is_running_method(self):
        worker = type("WakeWordWorker", (), {
            "running": True,
            "is_running": lambda self: self.running,
        })()
        self.assertTrue(threading_compat.worker_is_running(worker))
        worker.running = False
        self.assertFalse(threading_compat.worker_is_running(worker))

    def test_wait_for_workers_returns_when_all_workers_stopped(self):
        workers = [self.FakeWorker(stopped=True), self.FakeWorker(stopped=True)]
        with patch("time.sleep") as mock_sleep:
            threading_compat.wait_for_workers(workers, poll_interval=0.1)
        mock_sleep.assert_not_called()

    def test_wait_for_workers_polls_until_workers_stop(self):
        workers = [self.FakeWorker(stopped=False)]

        def stop_after_poll(*args, **kwargs):
            workers[0].stopped = True

        with patch("time.sleep", side_effect=stop_after_poll):
            threading_compat.wait_for_workers(workers, poll_interval=0.1)

        self.assertTrue(workers[0].stopped)


if __name__ == "__main__":
    unittest.main()
