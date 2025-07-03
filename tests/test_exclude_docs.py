import unittest

from scripts import check_exclude_docs  # noqa: E402


class TestExcludeDocs(unittest.TestCase):
    def test_main_matches(self):
        self.assertEqual(check_exclude_docs.main(), 0)


if __name__ == "__main__":
    unittest.main()
