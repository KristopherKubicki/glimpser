"""Portable lock semantics; also run directly on native packaging runners."""

import tempfile
import unittest
from pathlib import Path

from app.utils import file_locks


class FileLockTests(unittest.TestCase):
    def test_nonblocking_contention_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.lock"
            with path.open("a+b") as first, path.open("a+b") as second:
                file_locks.flock(first, file_locks.LOCK_EX | file_locks.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    file_locks.flock(second, file_locks.LOCK_EX | file_locks.LOCK_NB)
                file_locks.flock(first, file_locks.LOCK_UN)
                file_locks.flock(second, file_locks.LOCK_EX | file_locks.LOCK_NB)
                file_locks.flock(second, file_locks.LOCK_UN)

    def test_descriptor_position_and_close_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.lock"
            path.write_bytes(b"position")
            with path.open("r+b") as first:
                first.seek(3)
                file_locks.flock(first.fileno(), file_locks.LOCK_EX)
                self.assertEqual(first.tell(), 3)
            with path.open("r+b") as second:
                file_locks.flock(
                    second.fileno(), file_locks.LOCK_EX | file_locks.LOCK_NB
                )


if __name__ == "__main__":
    unittest.main()
