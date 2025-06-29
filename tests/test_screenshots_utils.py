"""Tests for screenshots utils."""
import os
import shutil
import tempfile
import time
import unittest

from app.utils.screenshots import cleanup_old_tempdirs, run_cmd


class TestRunCmd(unittest.TestCase):
    def test_run_cmd_success(self):
        out = run_cmd(["bash", "-c", "echo -n hello"], timeout=5)
        self.assertEqual(out, b"hello")

    def test_run_cmd_error(self):
        with self.assertRaises(RuntimeError):
            run_cmd(["bash", "-c", "echo error >&2; exit 1"], timeout=5)

    def test_run_cmd_timeout(self):
        start = time.time()
        with self.assertRaises(RuntimeError) as cm:
            run_cmd(["sleep", "2"], timeout=0.1)
        self.assertIn("timeout", str(cm.exception))
        self.assertLess(time.time() - start, 1)


class TestCleanupOldTempdirs(unittest.TestCase):
    def test_cleanup_removes_old_dirs(self):
        old_dir = tempfile.mkdtemp(prefix="glimpser_test_")
        new_dir = tempfile.mkdtemp(prefix="glimpser_test_")
        now = time.time()
        # make old_dir appear 2 hours old
        os.utime(old_dir, (now - 7200, now - 7200))
        os.utime(new_dir, (now, now))
        cleanup_old_tempdirs(prefix="glimpser_test_", max_age_hours=1)
        self.assertFalse(os.path.exists(old_dir))
        self.assertTrue(os.path.exists(new_dir))
        shutil.rmtree(new_dir)


if __name__ == "__main__":
    unittest.main()
