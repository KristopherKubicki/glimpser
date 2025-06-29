"""Tests for llm cache module."""
import os
import tempfile
import unittest
from unittest.mock import patch

from app.utils import llm_cache


class TestLLMCacheModule(unittest.TestCase):
    def test_key_uniqueness(self):
        first = llm_cache._key("p", ["a.png", "b.png"])
        second = llm_cache._key("p", ["b.png", "a.png"])
        self.assertEqual(first, llm_cache._key("p", ["a.png", "b.png"]))
        self.assertNotEqual(first, second)

    def test_persist_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = os.path.join(tmpdir, "cache.json")
            with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}):
                with patch("app.utils.llm_cache.CACHE_PATH", cache_path):
                    llm_cache._cache.clear()
                    llm_cache.store("p", "r", 1, ["x.png"])
                    self.assertTrue(os.path.exists(cache_path))
                    llm_cache._cache.clear()
                    llm_cache._load_cache()
                    entry = llm_cache.get("p", ["x.png"])
                    self.assertEqual(entry["response"], "r")
                    self.assertEqual(entry["tokens"], 1)


if __name__ == "__main__":
    unittest.main()
