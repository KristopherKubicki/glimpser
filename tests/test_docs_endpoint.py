"""Tests for docs endpoint."""
import os
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes import init_routes


class TestDocsEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        self.temp_dir = tempfile.TemporaryDirectory()
        with open(
            os.path.join(self.temp_dir.name, "test.md"), "w", encoding="utf-8"
        ) as fh:
            fh.write("content")
        self.docs_patch = patch("app.routes.DOCS_DIRECTORY", self.temp_dir.name)
        self.docs_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.docs_patch.stop()
        self.temp_dir.cleanup()

    def test_serves_doc_file(self):
        resp = self.client.get("/docs/test.md")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, b"content")


if __name__ == "__main__":
    unittest.main()
