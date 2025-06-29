import os
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

import app.utils.scheduling as scheduling
from app.utils.validators import validate_group_name


class TestGroupSymlinkWarning(unittest.TestCase):
    def test_blank_groups_do_not_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            cam_dir = os.path.join(tmp, "cam1")
            os.makedirs(cam_dir)
            shot = os.path.join(cam_dir, "cam1_20240101000000.png")
            Image.new("RGB", (10, 10)).save(shot)

            template = {
                "name": "cam1",
                "url": "",
                "motion": 0,
                "groups": ",g1,,g2,",
            }

            db_path = os.path.join(tmp, "test.db")
            with (
                patch.dict(os.environ, {"GLIMPSER_DATABASE_PATH": db_path}),
                patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", tmp),
                patch("app.utils.scheduling.capture_or_download", return_value=True),
                patch("app.utils.scheduling.add_timestamp"),
                patch("app.utils.scheduling.remove_background"),
                patch("app.utils.scheduling.add_motion_and_caption"),
                patch("app.utils.scheduling.save_template"),
                patch("app.utils.scheduling.send_http_callback"),
                patch("app.utils.scheduling.chatgpt_compare", return_value="cap"),
                patch("app.utils.scheduling.is_mostly_blank", return_value=False),
                patch("app.utils.scheduling.get_template", return_value=template),
                patch(
                    "app.utils.scheduling.validate_group_name",
                    wraps=validate_group_name,
                ) as mock_validate,
                patch("app.utils.scheduling.logging.warning") as mock_warn,
            ):
                scheduling.update_camera("cam1", template)

            mock_warn.assert_not_called()
            called_args = [c.args[0] for c in mock_validate.call_args_list]
            self.assertNotIn("", called_args)
            self.assertTrue(os.path.islink(os.path.join(tmp, "g1_latest_camera.png")))
            self.assertTrue(os.path.islink(os.path.join(tmp, "g2_latest_camera.png")))


if __name__ == "__main__":
    unittest.main()
