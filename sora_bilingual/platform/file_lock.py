"""Process-owned preparation locks, released even if a worker is terminated."""

import errno
import os
import time
from contextlib import contextmanager


@contextmanager
def preparation_lock(output, name="model-preparation.lock"):
    """UI prewarm and backend share the catalog; recheck caches after this lock.

    OS ownership releases on process exit, including a killed compiler. Never
    use the game/backend lock: preparing resources must not attach a process.
    """
    output.mkdir(parents=True, exist_ok=True)
    with (output / name).open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0, 2)
            if not lock.tell():
                lock.write(b"\0")
                lock.flush()
            while True:
                lock.seek(0)
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
