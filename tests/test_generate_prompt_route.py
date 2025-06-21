import os
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestGeneratePromptRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.prompt_optimizer.generate_prompt")
    def test_generate_prompt_success(self, mock_gen):
        mock_gen.return_value = "Test caption"
        resp = self.client.post("/generate_prompt/cam1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"prompt": "Test caption"})
        mock_gen.assert_called_with("cam1")

    @patch("app.routes.prompt_optimizer.generate_prompt", return_value="")
    def test_generate_prompt_no_images(self, mock_gen):
        resp = self.client.post("/generate_prompt/cam1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"prompt": ""})
        mock_gen.assert_called_with("cam1")


if __name__ == "__main__":
    unittest.main()
