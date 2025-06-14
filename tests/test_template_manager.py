import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.utils.template_manager import (
    Template,
    TemplateManager,
    get_storage_usage,
    get_storage_usage_bytes,
    get_templates,
    mark_offline,
    set_capture_failed,
    update_last_screenshot_time,
)
from app.utils.validators import validate_template_name


class TestTemplateManager(unittest.TestCase):
    def setUp(self):
        self.template_manager = TemplateManager()

    def tearDown(self):
        # Clean up any resources after each test if needed
        pass

    @patch("app.utils.template_manager.SessionLocal")
    def test_get_templates(self, mock_session):
        # Mock the session and query
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_query = mock_session_instance.query.return_value
        mock_all = mock_query.all

        # Create some mock templates
        mock_template1 = Template(name="template1", frequency=60)
        mock_template2 = Template(name="template2", frequency=120)
        mock_all.return_value = [mock_template1, mock_template2]

        # Call the method
        result = self.template_manager.get_templates()

        # Assert the result
        self.assertEqual(len(result), 2)
        self.assertIn("template1", result)
        self.assertIn("template2", result)
        self.assertEqual(result["template1"]["frequency"], 60)
        self.assertEqual(result["template2"]["frequency"], 120)

    @patch("app.utils.template_manager.SessionLocal")
    def test_get_templates_by_last_caption_time(self, mock_session):
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_query = mock_session_instance.query.return_value
        mock_order = mock_query.order_by
        mock_all = mock_order.return_value.all

        t1 = Template(name="t1", last_caption_time="2023-01-01 00:00:00")
        t2 = Template(name="t2", last_caption_time="2023-01-02 00:00:00")
        t3 = Template(name="t3", last_caption_time="2023-01-03 00:00:00")
        mock_all.return_value = [t3, t2, t1]

        result = self.template_manager.get_templates_by_last_caption_time()

        self.assertEqual(result[0][0], "t3")
        self.assertEqual(result[1][0], "t2")
        self.assertEqual(result[2][0], "t1")
        mock_order.assert_called()

    @patch("app.utils.template_manager.SessionLocal")
    def test_save_template(self, mock_session):
        # Mock the session and query
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_query = mock_session_instance.query.return_value
        mock_filter_by = mock_query.filter_by
        mock_first = mock_filter_by.return_value.first

        # Test creating a new template
        mock_first.return_value = None
        template_details = {"name": "new_template", "frequency": 30, "timeout": 5}
        self.template_manager.save_template("new_template", template_details)

        # Assert that a new Template was added to the session
        mock_session_instance.add.assert_called_once()
        mock_session_instance.commit.assert_called_once()

        # Test updating an existing template
        mock_existing_template = MagicMock()
        mock_first.return_value = mock_existing_template
        template_details = {"name": "existing_template", "frequency": 60, "timeout": 10}
        self.template_manager.save_template("existing_template", template_details)

        # Assert that the existing template was updated
        self.assertEqual(mock_existing_template.name, "existing_template")
        self.assertEqual(mock_existing_template.frequency, 60)
        self.assertEqual(mock_existing_template.timeout, 10)
        mock_session_instance.commit.assert_called()

    @patch("app.utils.template_manager.SessionLocal")
    def test_get_template(self, mock_session):
        # Mock the session and query
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_query = mock_session_instance.query.return_value
        mock_filter_by = mock_query.filter_by
        mock_first = mock_filter_by.return_value.first

        # Test getting an existing template
        mock_template = Template(name="test_template", frequency=90)
        mock_first.return_value = mock_template

        result = self.template_manager.get_template("test_template")

        self.assertEqual(result["name"], "test_template")
        self.assertEqual(result["frequency"], 90)

        # Test getting a non-existent template
        mock_first.return_value = None

        result = self.template_manager.get_template("non_existent")

        self.assertEqual(result, {})

    @patch("app.utils.template_manager.SessionLocal")
    def test_delete_template(self, mock_session):
        # Mock the session and query
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_query = mock_session_instance.query.return_value
        mock_filter_by = mock_query.filter_by
        mock_first = mock_filter_by.return_value.first

        # Test deleting an existing template
        mock_template = MagicMock()
        mock_first.return_value = mock_template

        result = self.template_manager.delete_template("existing_template")

        self.assertTrue(result)
        mock_session_instance.delete.assert_called_once_with(mock_template)
        mock_session_instance.commit.assert_called_once()

        # Test deleting a non-existent template
        mock_first.return_value = None

        result = self.template_manager.delete_template("non_existent")

        self.assertFalse(result)
        mock_session_instance.delete.assert_called_once()  # Should not be called again
        mock_session_instance.commit.assert_called_once()  # Should not be called again

    @patch("app.utils.template_manager.SessionLocal")
    def test_invalid_template_names(self, _):
        invalid_names = [
            "",
            "invalid name",
            "too_long_name_" * 5,
            "name_with_$pecial_chars",
        ]

        for name in invalid_names:
            result = self.template_manager.save_template(name, {"frequency": 60})
            self.assertFalse(result, f"Expected False for invalid name: {name}")

            result = self.template_manager.get_template(name)
            self.assertFalse(result, f"Expected False for invalid name: {name}")

            result = self.template_manager.delete_template(name)
            self.assertFalse(result, f"Expected False for invalid name: {name}")

    @patch("app.utils.template_manager.SessionLocal")
    def test_save_template_edge_cases(self, mock_session):
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_query = mock_session_instance.query.return_value
        mock_filter_by = mock_query.filter_by
        mock_first = mock_filter_by.return_value.first
        mock_first.return_value = None  # Simulate creating a new template

        self.template_manager.save_template("test_template", {"frequency": 525601})
        args, _ = mock_session_instance.add.call_args
        self.assertEqual(args[0].frequency, 525600)

        mock_session_instance.add.reset_mock()

        result = self.template_manager.save_template(
            "test_template2", {"frequency": 1, "timeout": 120}
        )
        self.assertFalse(result)
        self.assertEqual(mock_session_instance.commit.call_count, 1)

    @patch("app.utils.template_manager.SessionLocal")
    def test_browser_and_stealth_defaults(self, mock_session):
        """Browser/stealth templates should receive higher defaults."""

        mock_sess = MagicMock()
        mock_session.return_value = mock_sess
        mock_query = mock_sess.query.return_value
        mock_first = mock_query.filter_by.return_value.first
        mock_first.return_value = None  # simulate creation

        self.template_manager.save_template("btemp", {"browser": True})
        args, _ = mock_sess.add.call_args
        self.assertEqual(args[0].frequency, 60)
        self.assertEqual(args[0].timeout, 30)

        mock_sess.add.reset_mock()

        self.template_manager.save_template("stemp", {"stealth": True})
        args, _ = mock_sess.add.call_args
        self.assertEqual(args[0].frequency, 60)
        self.assertEqual(args[0].timeout, 30)

    @patch("app.utils.template_manager.SessionLocal")
    def test_get_template_by_id(self, mock_session):
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_query = mock_session_instance.query.return_value
        mock_filter_by = mock_query.filter_by
        mock_first = mock_filter_by.return_value.first

        # Test getting an existing template by ID
        mock_template = Template(id=1, name="test_template", frequency=90)
        mock_first.return_value = mock_template

        result = self.template_manager.get_template_by_id(1)

        self.assertEqual(result["id"], 1)
        self.assertEqual(result["name"], "test_template")
        self.assertEqual(result["frequency"], 90)

        # Test getting a non-existent template by ID
        mock_first.return_value = None

        result = self.template_manager.get_template_by_id(999)

        self.assertEqual(result, {})

    @patch("app.utils.template_manager.SessionLocal")
    def test_get_template_by_id_invalid(self, mock_session):
        """Invalid IDs should short circuit and not hit the DB."""

        # Negative ID
        result = self.template_manager.get_template_by_id(-1)
        self.assertEqual(result, {})
        mock_session.assert_not_called()

        # Zero ID
        result = self.template_manager.get_template_by_id(0)
        self.assertEqual(result, {})
        mock_session.assert_not_called()

        # Non integer ID
        result = self.template_manager.get_template_by_id("abc")
        self.assertEqual(result, {})
        mock_session.assert_not_called()


class TestValidateTemplateName(unittest.TestCase):
    """Tests for the ``validate_template_name`` utility."""

    def test_valid_names(self):
        """Names containing allowed characters should be returned unchanged."""
        self.assertEqual(validate_template_name("cam1"), "cam1")
        self.assertEqual(validate_template_name("cam-02"), "cam-02")

    def test_invalid_names(self):
        """Invalid names should return ``None``."""
        invalid = [
            "",
            "-cam",
            "cam-",
            "_cam",
            "cam_",
            "cam name",
            "cam$name",
            "cam..01",
            "cam--01",
        ]
        for name in invalid:
            self.assertIsNone(
                validate_template_name(name),
                msg=f"{name} should be invalid",
            )


class TestOfflineHandling(unittest.TestCase):
    @patch("app.utils.template_manager.SessionLocal")
    def test_mark_offline_sets_timestamp(self, mock_session):
        mock_sess = MagicMock()
        mock_session.return_value = mock_sess
        template = Template(name="cam1")
        mock_sess.query.return_value.filter_by.return_value.first.return_value = (
            template
        )

        mark_offline("cam1")

        self.assertNotEqual(template.offline_since, "")
        mock_sess.commit.assert_called_once()

    @patch("app.utils.template_manager.SessionLocal")
    def test_update_last_screenshot_time_clears_offline(self, mock_session):
        mock_sess = MagicMock()
        mock_session.return_value = mock_sess
        template = Template(name="cam1", offline_since="yesterday")
        mock_sess.query.return_value.filter_by.return_value.first.return_value = (
            template
        )

        update_last_screenshot_time("cam1")

        self.assertEqual(template.offline_since, "")
        self.assertNotEqual(template.last_screenshot_time, "")
        mock_sess.commit.assert_called_once()

    @patch("app.utils.template_manager.SessionLocal")
    def test_set_capture_failed_updates_flag(self, mock_session):
        mock_sess = MagicMock()
        mock_session.return_value = mock_sess
        template = Template(name="cam1")
        mock_sess.query.return_value.filter_by.return_value.first.return_value = (
            template
        )

        set_capture_failed("cam1", True)

        self.assertTrue(template.capture_failed)
        mock_sess.commit.assert_called_once()


class TestStorageUsage(unittest.TestCase):
    def test_get_storage_usage(self):
        """Combines screenshot and video sizes from both directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sshot_dir = os.path.join(temp_dir, "shots")
            vid_dir = os.path.join(temp_dir, "vid")
            os.makedirs(os.path.join(sshot_dir, "cam1"))
            os.makedirs(os.path.join(vid_dir, "cam1"))

            with open(os.path.join(sshot_dir, "cam1", "cam1.png"), "wb") as f:
                f.write(b"0" * 1024)
            with open(os.path.join(vid_dir, "cam1", "cam1.mp4"), "wb") as f:
                f.write(b"0" * 2048)

            with (
                patch("app.utils.template_manager.SCREENSHOT_DIRECTORY", sshot_dir),
                patch("app.utils.template_manager.VIDEO_DIRECTORY", vid_dir),
            ):
                result = get_storage_usage("cam1")
                self.assertEqual(result, "3.0 KB")

    def test_get_storage_usage_bytes(self):
        """Returns raw byte count for sorting."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sshot_dir = os.path.join(temp_dir, "shots")
            vid_dir = os.path.join(temp_dir, "vid")
            os.makedirs(os.path.join(sshot_dir, "cam1"))
            os.makedirs(os.path.join(vid_dir, "cam1"))

            with open(os.path.join(sshot_dir, "cam1", "cam1.png"), "wb") as f:
                f.write(b"0" * 1024)
            with open(os.path.join(vid_dir, "cam1", "cam1.mp4"), "wb") as f:
                f.write(b"0" * 2048)

            with (
                patch(
                    "app.utils.template_manager.SCREENSHOT_DIRECTORY",
                    sshot_dir,
                ),
                patch("app.utils.template_manager.VIDEO_DIRECTORY", vid_dir),
            ):
                result = get_storage_usage_bytes("cam1")
                self.assertEqual(result, 3072)


class TestSnapshotDetection(unittest.TestCase):
    @patch("app.utils.template_manager.SessionLocal")
    def test_snapshot_flag_in_get_templates(self, mock_session):
        mock_sess = MagicMock()
        mock_session.return_value = mock_sess
        mock_query = mock_sess.query.return_value
        mock_all = mock_query.all

        t1 = Template(name="cam1", url="http://example.com/snapshot.jpg")
        t2 = Template(name="cam2", url="http://example.com/stream.m3u8")
        mock_all.return_value = [t1, t2]

        result = get_templates()

        self.assertTrue(result["cam1"]["snapshot_only"])
        self.assertFalse(result["cam2"]["snapshot_only"])

    @patch("app.utils.template_manager.SessionLocal")
    def test_snapshot_flag_in_get_template(self, mock_session):
        mock_sess = MagicMock()
        mock_session.return_value = mock_sess
        mock_query = mock_sess.query.return_value
        mock_first = mock_query.filter_by.return_value.first

        t1 = Template(name="cam1", url="http://example.com/snapshot.jpg")
        mock_first.return_value = t1

        manager = TemplateManager()
        result = manager.get_template("cam1")

        self.assertTrue(result["snapshot_only"])


class TestSchedulerUpdates(unittest.TestCase):
    @patch("app.utils.scheduling.scheduler")
    @patch("app.utils.template_manager.SessionLocal")
    def test_save_template_reschedules_job(self, mock_session, mock_sched):
        """Updating a template should recreate its scheduled job."""

        mock_sess = MagicMock()
        mock_session.return_value = mock_sess
        template = Template(name="cam1", frequency=1)
        mock_sess.query.return_value.filter_by.return_value.first.return_value = (
            template
        )

        manager = TemplateManager()
        result = manager.save_template("cam1", {"frequency": 2})

        self.assertTrue(result)
        mock_sess.commit.assert_called_once()
        mock_sched.remove_job.assert_called_with("cam1")
        mock_sched.add_job.assert_called_once()


if __name__ == "__main__":
    unittest.main()
