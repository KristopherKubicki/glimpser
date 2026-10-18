import unittest

from app.utils.validators import event_buffer_eligibility, validate_update_data


class TestValidateUpdateData(unittest.TestCase):
    def test_defaults_and_ranges(self):
        data = {
            "url": "http://example",
            "frequency": "0",
            "timeout": "100000",
            "object_confidence": "2",
            "motion": "-1",
            "rollback_frames": "-5",
        }
        result = validate_update_data(data)
        self.assertEqual(result["frequency"], 1)
        self.assertLess(result["timeout"], result["frequency"] * 60)
        self.assertEqual(result["object_confidence"], 1.0)
        self.assertEqual(result["motion"], 0.0)
        self.assertEqual(result["rollback_frames"], 0)

    def test_missing_url_raises(self):
        with self.assertRaises(ValueError):
            validate_update_data({})

    def test_invalid_proxy_removed(self):
        data = {"url": "http://example", "proxy": "   "}
        result = validate_update_data(data)
        self.assertNotIn("proxy", result)

    def test_valid_proxy_preserved(self):
        data = {"url": "http://example", "proxy": "http://localhost:8080"}
        result = validate_update_data(data)
        self.assertEqual(result["proxy"], "http://localhost:8080")

    def test_stealth_defaults(self):
        data = {"url": "http://example", "stealth": True}
        result = validate_update_data(data)
        self.assertEqual(result["frequency"], 60)
        self.assertEqual(result["timeout"], 30)

    def test_browser_defaults(self):
        data = {"url": "http://example", "browser": True}
        result = validate_update_data(data)
        self.assertEqual(result["frequency"], 60)
        self.assertEqual(result["timeout"], 30)

    def test_disable_autocrop_boolean_is_preserved(self):
        data = {"url": "http://example", "disable_autocrop": True}
        result = validate_update_data(data)
        self.assertTrue(result["disable_autocrop"])

    def test_event_buffer_accepts_lan_camera_and_clamps_bounds(self):
        data = {
            "url": "http://192.168.1.20/snapshot.jpg",
            "event_buffer_enabled": "on",
            "event_buffer_fps": "9",
            "event_buffer_seconds": "999",
            "event_buffer_width": "2000",
            "event_buffer_pre_seconds": "999",
            "event_buffer_post_seconds": "999",
            "event_buffer_backoff_seconds": "1",
        }
        result = validate_update_data(data)
        self.assertTrue(result["event_buffer_enabled"])
        self.assertEqual(result["event_buffer_profile"], "lan_hardwired")
        self.assertEqual(result["event_buffer_fps"], 2)
        self.assertEqual(result["event_buffer_seconds"], 300)
        self.assertEqual(result["event_buffer_width"], 1280)
        self.assertEqual(result["event_buffer_pre_seconds"], 30)
        self.assertEqual(result["event_buffer_post_seconds"], 30)
        self.assertEqual(result["event_buffer_backoff_seconds"], 30)

    def test_event_buffer_rejects_public_url_when_enabled(self):
        data = {"url": "https://example.com/camera.jpg", "event_buffer_enabled": True}
        with self.assertRaisesRegex(ValueError, "private LAN camera"):
            validate_update_data(data)

    def test_event_buffer_rejects_browser_mode_when_enabled(self):
        data = {
            "url": "http://192.168.1.21/snapshot.jpg",
            "browser": True,
            "event_buffer_enabled": True,
        }
        with self.assertRaisesRegex(ValueError, "browser captures"):
            validate_update_data(data)

    def test_event_buffer_rejects_proxy_when_enabled(self):
        data = {
            "url": "http://192.168.1.22/snapshot.jpg",
            "proxy": "http://localhost:8080",
            "event_buffer_enabled": True,
        }
        with self.assertRaisesRegex(ValueError, "proxied captures"):
            validate_update_data(data)

    def test_event_buffer_rejects_eufy_scheme_when_enabled(self):
        data = {"url": "eufy://beach/pathway", "event_buffer_enabled": True}
        with self.assertRaisesRegex(ValueError, "HTTP"):
            validate_update_data(data)

    def test_event_buffer_eligibility_reports_disabled_reason(self):
        ok, reason = event_buffer_eligibility({"url": "http://127.0.0.1/snapshot.jpg"})
        self.assertFalse(ok)
        self.assertIn("private LAN camera", reason)


if __name__ == "__main__":
    unittest.main()
