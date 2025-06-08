import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import clean_logs  # noqa: E402


class TestCleanLogs(unittest.TestCase):
    def test_read_lines_strips_and_ignores_empty(self):
        lines = [" line1\n", "line2\n", "\n", "line3 "]
        result = clean_logs._read_lines(lines)
        self.assertEqual(result, ["line1", "line2", "line3"])

    def test_clean_lines_deduplicates_and_counts(self):
        lines = ["a", "b", "a", "c", "b", "a"]
        result = clean_logs.clean_lines(lines)
        self.assertEqual(result, ["[3] a", "[2] b", "c"])


if __name__ == "__main__":
    unittest.main()
