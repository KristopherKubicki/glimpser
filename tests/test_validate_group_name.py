"""Tests for validate group name."""
import unittest

from app.utils.validators import validate_group_name


class TestValidateGroupName(unittest.TestCase):
    def test_valid_names(self):
        self.assertEqual(validate_group_name("Group One"), "group_one")
        self.assertEqual(validate_group_name("group-1"), "group-1")

    def test_invalid_names(self):
        self.assertIsNone(validate_group_name("../evil"))
        self.assertIsNone(validate_group_name("bad/name"))
        self.assertIsNone(validate_group_name("bad..name"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
