"""Exclusive descriptor locks for capture workers on POSIX and Windows."""

import errno
import os
import time

__all__ = ["LOCK_EX", "LOCK_NB", "LOCK_UN", "flock"]

try:
    from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
except ImportError:  # pragma: no cover - exercised by the Windows package smoke test
    import msvcrt

    LOCK_EX, LOCK_NB, LOCK_UN = 2, 4, 8

    def flock(file, operation):
        """Lock byte zero of a Windows lockfile without changing its position."""
        descriptor = file if isinstance(file, int) else file.fileno()
        if operation not in {LOCK_EX, LOCK_EX | LOCK_NB, LOCK_UN}:
            raise ValueError("Only exclusive file locks are supported")
        position = os.lseek(descriptor, 0, os.SEEK_CUR)
        try:
            while True:
                os.lseek(descriptor, 0, os.SEEK_SET)
                try:
                    mode = msvcrt.LK_UNLCK if operation == LOCK_UN else msvcrt.LK_NBLCK
                    msvcrt.locking(descriptor, mode, 1)
                    return
                except OSError as exc:
                    if operation == LOCK_UN or exc.errno not in {
                        errno.EACCES,
                        errno.EAGAIN,
                        errno.EDEADLK,
                    }:
                        raise
                    if operation & LOCK_NB:
                        raise BlockingIOError(errno.EAGAIN, "File is locked") from exc
                    time.sleep(0.05)
        finally:
            os.lseek(descriptor, position, os.SEEK_SET)
