import os
import tempfile
import unittest

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
                safe_symlink(src, dst)
            finally:
                os.chdir(cwd)

            self.assertEqual(os.readlink(dst), os.path.abspath(os.path.join(tmp, src)))


if __name__ == "__main__":
    unittest.main()
