"""Unit tests for the BackgroundWorker action queue."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from background_worker import BackgroundWorker


class TestSubmit(unittest.TestCase):

    def setUp(self):
        self.logged = []
        self.worker = BackgroundWorker(
            name="test", max_queue=2, logger=self.logged.append
        )
        # Mark running without starting a real thread so run_pending() can be
        # driven deterministically.
        self.worker._running = True

    def test_submitted_actions_run_in_order(self):
        order = []
        self.worker.submit(order.append, 1)
        self.worker.submit(order.append, 2)

        self.assertEqual(self.worker.run_pending(), 2)
        self.assertEqual(order, [1, 2])

    def test_submit_does_not_run_the_action_inline(self):
        ran = []
        self.worker.submit(ran.append, "now")

        self.assertEqual(ran, [])
        self.assertEqual(self.worker.pending, 1)

    def test_submit_is_rejected_when_not_running(self):
        self.worker._running = False

        self.assertFalse(self.worker.submit(lambda: None))
        self.assertEqual(self.worker.pending, 0)
        self.assertEqual(self.worker.dropped_count, 1)

    def test_queue_is_bounded(self):
        self.assertTrue(self.worker.submit(lambda: None))
        self.assertTrue(self.worker.submit(lambda: None))
        self.assertFalse(self.worker.submit(lambda: None))

        self.assertEqual(self.worker.pending, 2)
        self.assertEqual(self.worker.dropped_count, 1)

    def test_dropping_is_logged(self):
        for _ in range(3):
            self.worker.submit(lambda: None)

        self.assertTrue(any("queue full" in line for line in self.logged))

    def test_space_frees_up_after_running(self):
        self.worker.submit(lambda: None)
        self.worker.submit(lambda: None)
        self.worker.run_pending()

        self.assertTrue(self.worker.submit(lambda: None))


class TestFailureIsolation(unittest.TestCase):

    def setUp(self):
        self.logged = []
        self.worker = BackgroundWorker(name="test", logger=self.logged.append)
        self.worker._running = True

    def test_a_failing_action_does_not_stop_later_ones(self):
        ran = []

        def boom():
            raise RuntimeError("speaker unavailable")

        self.worker.submit(boom)
        self.worker.submit(ran.append, "after")

        self.assertEqual(self.worker.run_pending(), 2)
        self.assertEqual(ran, ["after"])

    def test_a_failing_action_is_logged(self):
        def boom():
            raise RuntimeError("speaker unavailable")

        self.worker.submit(boom)
        self.worker.run_pending()

        self.assertTrue(
            any("RuntimeError" in line and "speaker unavailable" in line
                for line in self.logged)
        )

    def test_a_failing_logger_never_propagates(self):
        def bad_logger(_line):
            raise OSError("stdout is gone")

        worker = BackgroundWorker(name="test", max_queue=1, logger=bad_logger)
        worker._running = True
        worker.submit(lambda: None)
        worker.submit(lambda: None)  # dropped -> tries to log

        worker.run_pending()  # must not raise


class TestLifecycle(unittest.TestCase):

    def test_start_then_stop_runs_the_thread(self):
        worker = BackgroundWorker(name="test", poll_interval=0.001)
        worker.start()
        self.assertTrue(worker.is_running())

        done = []
        worker.submit(done.append, "ran")

        for _ in range(500):
            if done:
                break
            import time
            time.sleep(0.002)

        worker.stop()
        self.assertEqual(done, ["ran"])
        self.assertFalse(worker.is_running())

    def test_start_is_idempotent(self):
        worker = BackgroundWorker(name="test", poll_interval=0.001)
        worker.start()
        first_thread = worker._thread
        worker.start()

        self.assertIs(worker._thread, first_thread)
        worker.stop()

    def test_stop_abandons_pending_actions(self):
        worker = BackgroundWorker(name="test", max_queue=4)
        worker._running = True
        worker.submit(lambda: None)
        worker.stop()

        self.assertEqual(worker.pending, 0)

    def test_stop_without_start_is_safe(self):
        BackgroundWorker(name="test").stop()


if __name__ == "__main__":
    unittest.main()
