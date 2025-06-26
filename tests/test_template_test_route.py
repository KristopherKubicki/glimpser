import sys
import types
import unittest
from flask import Flask
from unittest.mock import patch

dummy_tf = types.ModuleType("transformers")
dummy_tf.CLIPProcessor = object
dummy_tf.CLIPModel = object
sys.modules.setdefault("transformers", dummy_tf)
skimage_mod = types.ModuleType("skimage")
metrics_mod = types.ModuleType("skimage.metrics")
metrics_mod.structural_similarity = lambda *a, **k: 0
skimage_mod.metrics = metrics_mod
sys.modules.setdefault("skimage", skimage_mod)
sys.modules.setdefault("skimage.metrics", metrics_mod)
sys.modules.setdefault("nodriver", types.ModuleType("nodriver"))

from app.routes import init_routes


class TestTemplateTestRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.template_manager.get_template")
    @patch("app.routes.template_tester.test_template_settings")
    def test_test_template_success(self, mock_test, mock_get):
        mock_get.return_value = {
            "url": "http://x",
            "popup_xpath": "",
            "dedicated_xpath": "",
        }
        mock_test.return_value = {"collector": "image"}
        resp = self.client.post("/test_template/cam1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"collector": "image"})

    @patch("app.routes.template_manager.get_template", return_value={})
    def test_test_template_not_found(self, mock_get):
        resp = self.client.post("/test_template/missing")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
