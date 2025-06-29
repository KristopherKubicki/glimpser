"""Tests for inject footer logging."""
import unittest
from unittest.mock import patch

from flask import Flask

import app.routes as routes


class TestInjectFooterLogging(unittest.TestCase):
    def test_update_error_logged(self):
        app = Flask(__name__)
        routes.init_routes(app)
        proc = None
        for p in app.template_context_processors[None]:
            if p.__name__ == "inject_footer_data":
                proc = p
                break
        with patch(
            "app.utils.github.is_update_available", side_effect=Exception("fail")
        ):
            with self.assertLogs(level="WARNING") as logs:
                with app.app_context():
                    data = proc()
        self.assertFalse(data["VERSION_OUTDATED"])
        self.assertIn("Could not determine update status", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
