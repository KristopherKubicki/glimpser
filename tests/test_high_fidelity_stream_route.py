import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from flask import Flask
from PIL import Image, ImageDraw

from app.routes import init_routes


class TestHighFidelityStreamRoute(unittest.TestCase):
    def setUp(self):
        self.repo_root = tempfile.mkdtemp(prefix="high_fidelity_")
        self.sshot_dir = os.path.join(self.repo_root, "screenshots")
        os.makedirs(self.sshot_dir, exist_ok=True)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.sc_patch = patch("app.routes.SCREENSHOT_DIRECTORY", self.sshot_dir)
        self.tpl_patch = patch("app.routes.template_manager.get_templates")
        self.blank_patch = patch(
            "app.routes.screenshots.is_mostly_blank", return_value=False
        )
        self.login_patch.start()
        self.sc_patch.start()
        self.mock_tpl = self.tpl_patch.start()
        self.blank_patch.start()
        self.app = Flask(__name__)
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.sc_patch.stop()
        self.tpl_patch.stop()
        self.blank_patch.stop()
        shutil.rmtree(self.repo_root, ignore_errors=True)

    def _write_camera_frame(self, name: str) -> None:
        cam_dir = os.path.join(self.sshot_dir, name)
        os.makedirs(cam_dir, exist_ok=True)
        img = Image.new("RGB", (640, 360), (20, 30, 40))
        draw = ImageDraw.Draw(img)
        draw.rectangle((50, 40, 590, 320), outline=(200, 220, 240), width=4)
        draw.line((0, 0, 639, 359), fill=(255, 180, 0), width=5)
        draw.text((30, 20), name, fill=(255, 255, 255))
        img.save(os.path.join(cam_dir, "latest_camera.png"))

    def test_high_fidelity_json_filters_sensitive_stale_and_broken_templates(self):
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self._write_camera_frame("BeachCam")
        self._write_camera_frame("PrivateSafe")
        self._write_camera_frame("LoadingCam")
        self._write_camera_frame("StaleCam")
        self.mock_tpl.return_value = {
            "BeachCam": {
                "name": "BeachCam",
                "groups": "beach,public",
                "notes": "Public lakefront",
                "capture_failed": False,
                "last_caption": "Clear lakefront skyline view.",
                "last_screenshot_time": now,
            },
            "PrivateSafe": {
                "name": "PrivateSafe",
                "groups": "example-home",
                "notes": "interior camera",
                "capture_failed": False,
                "private_camera": True,
                "last_caption": "Interior camera.",
                "last_screenshot_time": now,
            },
            "LoadingCam": {
                "name": "LoadingCam",
                "groups": "public",
                "notes": "Public plaza",
                "capture_failed": False,
                "last_caption": "Sign in page is still loading.",
                "last_screenshot_time": now,
            },
            "BrokenCam": {
                "name": "BrokenCam",
                "groups": "public",
                "notes": "Public plaza",
                "capture_failed": True,
                "last_caption": "Normal scene.",
                "last_screenshot_time": now,
            },
            "StaleCam": {
                "name": "StaleCam",
                "groups": "public",
                "notes": "Public plaza",
                "capture_failed": False,
                "last_caption": "Normal scene.",
                "last_screenshot_time": "2020-01-01 00:00:00",
            },
        }

        resp = self.client.get("/high_fidelity.json")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["profile"], "high_fidelity")
        self.assertEqual(data["count"], 1)
        self.assertEqual([row["name"] for row in data["items"]], ["BeachCam"])
        self.assertIn("/stream.png?camera=BeachCam", data["items"][0]["image_url"])
        self.assertIn("/last_video/BeachCam", data["items"][0]["video_url"])
        self.assertIn("/group/beach", data["items"][0]["group_url"])
        self.assertIn("/templates/BeachCam", data["items"][0]["template_url"])

    def test_high_fidelity_json_supports_group_and_override_excludes(self):
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self._write_camera_frame("ShowroomWide")
        self._write_camera_frame("BeachCam")
        self._write_camera_frame("JewelryCam")
        self.mock_tpl.return_value = {
            "ShowroomWide": {
                "name": "ShowroomWide",
                "groups": "example-home,public",
                "notes": "showroom public wall",
                "capture_failed": False,
                "last_caption": "Wide floor view.",
                "last_screenshot_time": now,
            },
            "BeachCam": {
                "name": "BeachCam",
                "groups": "beach,public",
                "notes": "Public lakefront",
                "capture_failed": False,
                "last_caption": "Clear lakefront skyline view.",
                "last_screenshot_time": now,
            },
            "JewelryCam": {
                "name": "JewelryCam",
                "groups": "example-home,public",
                "notes": "jewelry display overview",
                "capture_failed": False,
                "high_fidelity_mode": "include",
                "high_fidelity_rank": 25,
                "last_caption": "Wide sales floor view.",
                "last_screenshot_time": now,
            },
        }

        resp = self.client.get(
            "/high_fidelity.json?group=example-home&exclude=showroom"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual([row["name"] for row in data["items"]], ["JewelryCam"])
        self.assertEqual(data["items"][0]["high_fidelity_mode"], "include")
        self.assertEqual(data["items"][0]["high_fidelity_rank"], 25)

        resp = self.client.get("/high_fidelity.json?group=beach&include=lakefront")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual([row["name"] for row in data["items"]], ["BeachCam"])

    def test_high_fidelity_json_prefers_ranked_includes(self):
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self._write_camera_frame("AutoCam")
        self._write_camera_frame("RankedCam")
        self.mock_tpl.return_value = {
            "AutoCam": {
                "name": "AutoCam",
                "groups": "beach",
                "notes": "Public shoreline",
                "capture_failed": False,
                "last_caption": "Calm beach view.",
                "last_screenshot_time": now,
            },
            "RankedCam": {
                "name": "RankedCam",
                "groups": "beach",
                "notes": "Operator favorite shot",
                "capture_failed": False,
                "high_fidelity_mode": "include",
                "high_fidelity_rank": 80,
                "last_caption": "Pier and skyline.",
                "last_screenshot_time": now,
            },
        }

        resp = self.client.get("/high_fidelity.json?group=beach")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(
            [row["name"] for row in data["items"]],
            ["RankedCam", "AutoCam"],
        )

    def test_high_fidelity_mjpg_returns_stream(self):
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self._write_camera_frame("BeachCam")
        self.mock_tpl.return_value = {
            "BeachCam": {
                "name": "BeachCam",
                "groups": "beach,public",
                "notes": "Public lakefront",
                "capture_failed": False,
                "last_caption": "Clear lakefront skyline view.",
                "last_screenshot_time": now,
            }
        }

        resp = self.client.get(
            "/high_fidelity.mjpg?hold_s=2&transition_ms=0", buffered=False
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "multipart/x-mixed-replace")
        first = next(resp.response)
        second = next(resp.response)
        self.assertIn(b"--frame", first)
        self.assertIn(b"Content-Type: image/jpeg", second)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
