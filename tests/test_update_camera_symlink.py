import os
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from app.utils import scheduling


class TestUpdateCameraSymlink(unittest.TestCase):
    def test_handles_relative_prev_motion_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            cam_dir = os.path.join(tmp, "cam1")
            os.makedirs(cam_dir)
            img1 = os.path.join(cam_dir, "cam1_20260422145530.png")
            img2 = os.path.join(cam_dir, "cam1_20260422150205.png")
            Image.new("RGB", (10, 10)).save(img1)
            Image.new("RGB", (10, 10)).save(img2)

            os.symlink(
                "cam1_20260422145530.png", os.path.join(cam_dir, "last_motion.png")
            )

            template = {"name": "cam1", "motion": 0, "last_caption": "", "url": ""}

            with (
                patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", tmp),
                patch("app.utils.scheduling.capture_or_download", return_value=True),
                patch("app.utils.scheduling.add_timestamp"),
                patch("app.utils.scheduling.add_motion_and_caption"),
                patch("app.utils.scheduling.save_template"),
                patch("app.utils.scheduling.save_caption_metadata", return_value=True),
                patch("app.utils.scheduling.send_http_callback"),
                patch("app.utils.scheduling.chatgpt_compare", return_value="cap"),
                patch("app.utils.scheduling.is_mostly_blank", return_value=False),
                patch("app.utils.scheduling.get_template", return_value=template),
            ):
                scheduling.update_camera("cam1", template)

            self.assertTrue(os.path.islink(os.path.join(cam_dir, "prev_motion.png")))

    def test_removes_dangling_motion_sidecar_before_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cam_dir = os.path.join(tmp, "cam1")
            os.makedirs(cam_dir)
            newest = os.path.join(cam_dir, "cam1_20260422150205.png")
            Image.new("RGB", (10, 10)).save(newest)
            os.symlink("missing_frame.png", os.path.join(cam_dir, "last_motion.png"))

            template = {"name": "cam1", "motion": 0, "last_caption": "", "url": ""}

            with (
                patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", tmp),
                patch("app.utils.scheduling.capture_or_download", return_value=True),
                patch("app.utils.scheduling.add_timestamp"),
                patch("app.utils.scheduling.add_motion_and_caption"),
                patch("app.utils.scheduling.save_template"),
                patch("app.utils.scheduling.save_caption_metadata", return_value=True),
                patch("app.utils.scheduling.send_http_callback"),
                patch("app.utils.scheduling.chatgpt_compare", return_value="cap"),
                patch("app.utils.scheduling.is_mostly_blank", return_value=False),
                patch("app.utils.scheduling.update_last_screenshot_time"),
                patch("app.utils.scheduling.set_capture_failed"),
                patch("app.utils.scheduling.get_template", return_value=template),
            ):
                scheduling.update_camera("cam1", template)

            self.assertFalse(os.path.lexists(os.path.join(cam_dir, "prev_motion.png")))
            self.assertEqual(
                os.path.realpath(os.path.join(cam_dir, "last_motion.png")), newest
            )

    def test_source_template_renders_from_latest_base_screenshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = os.path.join(tmp, "basecam")
            os.makedirs(base_dir)
            base_name = "basecam_20260422010000.png"
            base_path = os.path.join(base_dir, base_name)
            Image.new("RGB", (24, 16), (90, 140, 180)).save(base_path)

            template = {
                "name": "derivedcam",
                "url": "http://should-not-run.example/cam.jpg",
                "source_template": "basecam",
                "motion": 1,
                "last_caption": "ready",
                "invert": False,
            }

            with (
                patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", tmp),
                patch(
                    "app.utils.scheduling.get_screenshots_for_template",
                    return_value=[base_name],
                ),
                patch("app.utils.scheduling.capture_or_download") as mock_capture,
                patch(
                    "app.utils.scheduling._postprocess_still_image",
                    side_effect=lambda image, *_args, **_kwargs: image.convert("RGB"),
                ),
                patch("app.utils.scheduling._is_valid_png", return_value=True),
                patch("app.utils.scheduling.add_timestamp"),
                patch("app.utils.scheduling.update_last_screenshot_time"),
                patch("app.utils.scheduling.set_capture_failed"),
                patch("app.utils.scheduling.get_template", return_value=template),
            ):
                scheduling.update_camera("derivedcam", template)

            mock_capture.assert_not_called()
            derived_dir = os.path.join(tmp, "derivedcam")
            created = [
                filename
                for filename in os.listdir(derived_dir)
                if filename.startswith("derivedcam_") and filename.endswith(".png")
            ]
            self.assertTrue(created)
            self.assertTrue(
                os.path.islink(os.path.join(derived_dir, "latest_camera.png"))
            )

    def test_update_camera_symlinks_follow_canonical_latest_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            cam_dir = os.path.join(tmp, "cam1")
            os.makedirs(cam_dir)

            newest = os.path.join(cam_dir, "cam1_20260422153026.png")
            older = os.path.join(cam_dir, "cam1_20260422145530.png")
            sidecar = os.path.join(cam_dir, "last_motion.png")

            Image.new("RGB", (24, 16), (90, 140, 180)).save(newest)
            Image.new("RGB", (24, 16), (80, 120, 160)).save(older)
            Image.new("RGB", (24, 16), (70, 100, 140)).save(sidecar)

            template = {
                "name": "cam1",
                "motion": 0,
                "last_caption": "",
                "url": "",
                "groups": "g1",
            }

            with (
                patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", tmp),
                patch("app.utils.scheduling.capture_or_download", return_value=True),
                patch("app.utils.scheduling.add_timestamp"),
                patch("app.utils.scheduling.add_motion_and_caption"),
                patch("app.utils.scheduling.save_template"),
                patch("app.utils.scheduling.save_caption_metadata", return_value=True),
                patch("app.utils.scheduling.send_http_callback"),
                patch("app.utils.scheduling.chatgpt_compare", return_value="cap"),
                patch("app.utils.scheduling.is_mostly_blank", return_value=False),
                patch("app.utils.scheduling.update_last_screenshot_time"),
                patch("app.utils.scheduling.set_capture_failed"),
                patch("app.utils.scheduling.get_template", return_value=template),
            ):
                scheduling.update_camera("cam1", template)

            latest_link = os.path.join(cam_dir, "latest_camera.png")
            group_link = os.path.join(tmp, "g1_latest_camera.png")
            global_link = os.path.join(tmp, "latest_camera.png")

            self.assertEqual(os.path.realpath(latest_link), newest)
            self.assertEqual(os.path.realpath(group_link), newest)
            self.assertEqual(os.path.realpath(global_link), newest)
            clean_path = os.path.join(cam_dir, "last_clean.png")
            self.assertTrue(os.path.exists(clean_path))
            with Image.open(clean_path) as clean:
                self.assertEqual(clean.getpixel((0, 0)), (90, 140, 180))


if __name__ == "__main__":
    unittest.main()
