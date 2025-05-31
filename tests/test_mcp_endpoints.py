import os
import sys
import unittest
from flask import Flask
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


class TestMcpEndpoints(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    def test_list_tools(self):
        resp = self.client.get("/mcp/tools")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        self.assertTrue(any(tool.get("name") == "echo" for tool in data))

    def test_call_tool(self):
        resp = self.client.post("/mcp/tool/echo", json={"text": "hello"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json().get("text"), "hello")
