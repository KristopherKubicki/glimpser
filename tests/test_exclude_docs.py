import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import check_exclude_docs  # noqa: E402


class TestExcludeDocs(unittest.TestCase):
    def test_main_matches(self):
        self.assertEqual(check_exclude_docs.main(), 0)


if __name__ == "__main__":
    unittest.main()
