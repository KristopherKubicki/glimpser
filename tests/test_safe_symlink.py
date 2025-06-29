import os
import tempfile
import unittest

from unittest.mock import patch

from app.utils.scheduling import safe_symlink


class TestSafeSymlink(unittest.TestCase):
    def test_replaces_existing_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            src1 = os.path.join(tmp, "f1")
            src2 = os.path.join(tmp, "f2")
            dst = os.path.join(tmp, "link")
            open(src1, "w").close()
            open(src2, "w").close()
            os.symlink(src1, dst)

            with patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", tmp):
                safe_symlink(src2, dst)

            self.assertEqual(os.readlink(dst), src2)

    def test_uses_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = "f"
            dst = os.path.join(tmp, "link")
            open(os.path.join(tmp, src), "w").close()
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", tmp):
                    safe_symlink(src, dst)
            finally:
                os.chdir(cwd)

            self.assertEqual(os.readlink(dst), os.path.abspath(os.path.join(tmp, src)))

    def test_rejects_outside_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "shots")
            os.makedirs(base)
            src = os.path.join(tmp, "f")
            dst = os.path.join(tmp, "link")
            open(src, "w").close()
            with patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", base):
                with self.assertRaises(ValueError):
                    safe_symlink(src, dst)


if __name__ == "__main__":
    unittest.main()
