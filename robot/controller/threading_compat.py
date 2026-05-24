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
