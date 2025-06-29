"""Tests for oui map."""
import os
import unittest

from app.utils.oui_map import OUI_MAP


class TestOUIMap(unittest.TestCase):
    def test_known_ouis(self):
        expected = {
            "000c29": "VMware",
            "001c42": "Apple",
            "0023ae": "Nintendo",
        }
        for prefix, vendor in expected.items():
            self.assertEqual(OUI_MAP.get(prefix), vendor)


if __name__ == "__main__":
    unittest.main()
