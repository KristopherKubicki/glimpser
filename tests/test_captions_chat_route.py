"""Tests for captions chat route."""
import os
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from app.routes import init_routes


class TestCaptionsChatRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.ask_question", return_value="Answer")
    @patch("app.routes.SessionLocal")
    def test_chat_success(self, mock_session, mock_ask):
        session = MagicMock()
        mock_session.return_value = session
        summary = MagicMock()
        summary.content = '{"1":"hi"}'
        query = MagicMock()
        query.order_by.return_value = query
        query.limit.return_value.all.return_value = [summary]
        session.query.return_value = query

        resp = self.client.post("/captions_chat", json={"question": "Hi"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"answer": "Answer", "truncated": False})
        mock_ask.assert_called_once()

    def test_chat_missing_question(self):
        resp = self.client.post("/captions_chat", json={})
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
