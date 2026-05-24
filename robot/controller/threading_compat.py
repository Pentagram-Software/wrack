"""Threading helpers compatible with Pybricks MicroPython.

Pybricks MicroPython provides threading.Thread but not threading.Lock.
Use create_lock() anywhere a mutex is needed on EV3 or desktop Python.
"""

import threading


def create_lock():
    """Return a lock object usable as a context manager."""
    lock_factory = getattr(threading, "Lock", None)
    if lock_factory is not None:
        return lock_factory()

    try:
        import _thread
    except ImportError:
        _thread = None

    if _thread is not None and hasattr(_thread, "allocate_lock"):
        return _thread.allocate_lock()

    return _NoOpLock()


class _NoOpLock:
    """Fallback lock when the runtime has no threading primitives."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def acquire(self, *args, **kwargs):
        return True

    def release(self):
        pass

    def locked(self):
        return False


def worker_is_running(worker):
    """Return True if a worker thread is still active."""
    if worker is None:
        return False

    if hasattr(worker, "stopped"):
        return not worker.stopped

    is_running = getattr(worker, "is_running", None)
    if callable(is_running):
        return bool(is_running())

    running = getattr(worker, "running", None)
    if running is not None:
        return running

    is_alive = getattr(worker, "is_alive", None)
    if callable(is_alive):
        try:
            return is_alive()
        except Exception:
            pass

    return False


def wait_for_workers(workers, poll_interval=0.5):
    """Block until every worker thread has stopped.

    Pybricks MicroPython provides threading.Thread but not join(), so callers
    must poll worker state instead of calling thread.join().
    """
    from time import sleep

    while True:
        if not any(worker_is_running(worker) for worker in workers):
            break
        sleep(poll_interval)
