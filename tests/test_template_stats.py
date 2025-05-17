import os
import sys
import types
import tempfile
import shutil
import unittest
from unittest.mock import patch
import importlib.util


class TestTemplateStats(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.template_name = "sample"

        # Create minimal stub modules so template_manager can be imported
        sqlalchemy_stub = types.ModuleType("sqlalchemy")
        sqlalchemy_stub.Boolean = object
        sqlalchemy_stub.Column = lambda *a, **k: None
        sqlalchemy_stub.Float = object
        sqlalchemy_stub.Integer = object
        sqlalchemy_stub.String = object
        sqlalchemy_stub.Text = object
        orm_stub = types.ModuleType("sqlalchemy.orm")
        orm_stub.validates = lambda *a, **k: (lambda f: f)
        sqlalchemy_stub.orm = orm_stub
        sys.modules["sqlalchemy"] = sqlalchemy_stub
        sys.modules["sqlalchemy.orm"] = orm_stub

        db_stub = types.ModuleType("app.utils.db")
        db_stub.Base = object
        db_stub.SessionLocal = lambda: None
        db_stub.init_db = lambda: None
        sys.modules["app.utils.db"] = db_stub

        config_stub = types.ModuleType("app.config")
        config_stub.SCREENSHOT_DIRECTORY = "data/screenshots/"
        config_stub.VIDEO_DIRECTORY = "data/video/"
        sys.modules["app.config"] = config_stub

        video_details_stub = types.ModuleType("app.utils.video_details")
        video_details_stub.get_latest_screenshot_date = lambda x: None
        video_details_stub.get_latest_video_date = lambda x: None
        sys.modules["app.utils.video_details"] = video_details_stub

        werkzeug_utils_stub = types.ModuleType("werkzeug.utils")
        werkzeug_utils_stub.secure_filename = lambda x: x
        sys.modules["werkzeug.utils"] = werkzeug_utils_stub

        module_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "app", "utils", "template_manager.py")
        )
        sys.modules.setdefault("app", types.ModuleType("app"))
        sys.modules.setdefault("app.utils", types.ModuleType("app.utils"))
        spec = importlib.util.spec_from_file_location(
            "app.utils.template_manager", module_path
        )
        self.template_manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.template_manager)

        # directories for screenshots and videos
        self.screenshot_root = os.path.join(self.temp_dir, "screenshots")
        self.video_root = os.path.join(self.temp_dir, "videos")
        os.makedirs(os.path.join(self.screenshot_root, self.template_name))
        os.makedirs(os.path.join(self.video_root, self.template_name))

        # create sample screenshot files
        for i in range(2):
            path = os.path.join(
                self.screenshot_root,
                self.template_name,
                f"{self.template_name}_{i}.png",
            )
            with open(path, "wb") as f:
                f.write(b"a" * 10)

        # create sample video file
        vpath = os.path.join(
            self.video_root,
            self.template_name,
            f"{self.template_name}_0.mp4",
        )
        with open(vpath, "wb") as f:
            f.write(b"a" * 20)

        # patch directories used by template_manager
        self.patcher_ss = patch.object(
            self.template_manager,
            "SCREENSHOT_DIRECTORY",
            self.screenshot_root + "/",
        )
        self.patcher_vid = patch.object(
            self.template_manager,
            "VIDEO_DIRECTORY",
            self.video_root + "/",
        )
        self.patcher_ss.start()
        self.patcher_vid.start()

    def tearDown(self):
        self.patcher_ss.stop()
        self.patcher_vid.stop()
        shutil.rmtree(self.temp_dir)

    def test_counts_and_storage(self):
        sc_count = self.template_manager.get_screenshot_count(self.template_name)
        vd_count = self.template_manager.get_video_count(self.template_name)
        usage = self.template_manager.get_storage_usage(self.template_name)

        self.assertEqual(sc_count, 2)
        self.assertEqual(vd_count, 1)
        self.assertEqual(usage, "40.0 B")


if __name__ == "__main__":
    unittest.main()
