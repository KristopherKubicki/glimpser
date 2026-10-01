import unittest
from unittest.mock import patch

import app


class TestStatusDashboard(unittest.TestCase):
    def setUp(self):
        # Disable authentication before routes are registered so the
        # dashboard can be accessed without a session.
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.session_patch = patch("app.routes.session", {"user_id": 1})
        self.login_patch.start()
        self.session_patch.start()
        self.app = app.create_app(
            enable_watchdog=False, schedule=False, log_cache=False
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.session_patch.stop()

    def test_status_page_has_dashboard(self):
        resp = self.client.get("/status", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Feed Status", resp.data)

    @patch("app.utils.camera_health.build_camera_health_report")
    @patch("app.routes.template_manager.get_templates")
    @patch("app.routes.scheduling.get_system_metrics")
    def test_system_glimpse_page_has_operator_summary(
        self, mock_metrics, mock_templates, mock_health
    ):
        mock_metrics.return_value = {
            "cpu_usage": 12,
            "memory_usage": 34,
            "disk_usage": 56,
            "uptime": "4h 2m",
        }
        mock_templates.return_value = {"CameraA": {"groups": "example-site"}}
        mock_health.return_value = {
            "summary": {"capture_failing": 1},
            "cameras": [
                {
                    "name": "CameraA",
                    "groups": ["example-site"],
                    "status": "failing",
                    "capture_failed": True,
                    "severity": 3,
                    "last_screenshot_age_minutes": 42,
                    "issues": ["capture_failed=1"],
                }
            ],
        }

        with (
            patch(
                "app.blueprints.status.VIEWER_CONFIG",
                {"status_groups": ["example-site"]},
            ),
            patch(
                "app.blueprints.status.render_template",
                return_value="System Glimpse CameraA",
            ) as render,
        ):
            resp = self.client.get("/system_glimpse")

        self.assertEqual(
            render.call_args.kwargs["group_rows"],
            [{"name": "example-site", "total": 1, "failing": 1, "ok": 0}],
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"System Glimpse", resp.data)
        self.assertIn(b"CameraA", resp.data)


if __name__ == "__main__":
    unittest.main()
