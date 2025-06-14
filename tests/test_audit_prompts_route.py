import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestAuditPromptsRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.prompt_optimizer.audit_prompts")
    def test_audit_prompts(self, mock_audit):
        mock_audit.return_value = {"cam1": "Better"}
        resp = self.client.post("/audit_prompts")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"cam1": "Better"})
        mock_audit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
