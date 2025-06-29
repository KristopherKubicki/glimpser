"""Tests for clip gpu available."""
import unittest
from unittest.mock import MagicMock, patch

import app.routes as routes


class TestClipGpuAvailable(unittest.TestCase):
    def setUp(self):
        routes.clip_gpu_available.cache_clear()

    def test_returns_false_when_ort_missing(self):
        with patch.object(routes, "ort", None):
            routes.clip_gpu_available.cache_clear()
            self.assertFalse(routes.clip_gpu_available())

    def test_provider_check_and_cache(self):
        class MockOrt:
            def __init__(self, providers):
                self._providers = providers

            def get_available_providers(self):
                return self._providers

        with patch.object(routes, "ort", MockOrt(["CUDAExecutionProvider"])):
            routes.clip_gpu_available.cache_clear()
            self.assertTrue(routes.clip_gpu_available())
            # Change providers but expect cached value
            with patch.object(routes, "ort", MockOrt([])):
                self.assertTrue(routes.clip_gpu_available())
            routes.clip_gpu_available.cache_clear()
            with patch.object(routes, "ort", MockOrt([])):
                self.assertFalse(routes.clip_gpu_available())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
