import datetime
import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Summary
from app.utils import scheduling


class TestSummaryStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.addCleanup(self.temp_dir.cleanup)
        engine = create_engine(f"sqlite:///{self.db_path}")
        self.addCleanup(engine.dispose)
        Summary.__table__.create(engine)
        self.session_factory = sessionmaker(bind=engine)
        for target, value in (
            ("SessionLocal", self.session_factory),
            ("Summary", Summary),
            ("SUMMARIES_DIRECTORY", os.path.join(self.temp_dir.name, "summaries")),
        ):
            patcher = patch.object(scheduling, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target in ("email_alert", "sms_alert"):
            patcher = patch.object(scheduling, target)
            patcher.start()
            self.addCleanup(patcher.stop)

    @patch(
        "app.utils.scheduling.get_templates_sorted_by_last_caption_time",
        return_value=[],
    )
    @patch("app.utils.scheduling.summarize", return_value='{"1":"foo"}')
    def test_update_summary_saves_to_db(self, mock_sum, mock_get_templates):
        scheduling.update_summary()
        session = self.session_factory()
        try:
            rows = session.query(Summary).all()
            self.assertGreaterEqual(len(rows), 1)
        finally:
            session.close()

    @patch("app.utils.scheduling.get_templates_sorted_by_last_caption_time")
    @patch("app.utils.scheduling.summarize")
    def test_update_summary_skips_private_camera(self, mock_summarize, mock_templates):
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        mock_templates.return_value = [
            (
                "PublicCam",
                {
                    "name": "PublicCam",
                    "groups": "beach",
                    "notes": "Public shoreline",
                    "last_caption": "Clear skyline view.",
                    "last_caption_time": now,
                    "private_camera": False,
                },
            ),
            (
                "PrivateCam",
                {
                    "name": "PrivateCam",
                    "groups": "example-home",
                    "notes": "Office interior",
                    "last_caption": "Interior camera.",
                    "last_caption_time": now,
                    "private_camera": True,
                },
            ),
        ]

        def _summarize(prompt, history=""):
            self.assertIn("PublicCam", prompt)
            self.assertNotIn("PrivateCam", prompt)
            return '{"1":"ok"}'

        mock_summarize.side_effect = _summarize

        scheduling.update_summary()
        mock_summarize.assert_called_once()

    @patch("app.utils.scheduling.get_templates_sorted_by_last_caption_time")
    @patch("app.utils.scheduling.summarize", return_value='{"1":"ok"}')
    def test_summary_privacy_handles_stored_flags_and_group_case(
        self, mock_summarize, mock_templates
    ):
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        cases = [
            (True, "beach", False),
            ("true", "beach", False),
            (1, "beach", False),
            (False, "Private", False),
            (False, "beach, PRIVATE", False),
            ("false", "beach", True),
            (False, "beach", True),
        ]
        for flag, groups, included in cases:
            with self.subTest(flag=flag, groups=groups):
                mock_templates.return_value = [
                    (
                        "CameraMarker",
                        {
                            "name": "CameraMarker",
                            "groups": groups,
                            "private_camera": flag,
                            "notes": "Sensitive prompt marker",
                            "last_caption": "Sensitive caption marker. More detail.",
                            "last_caption_time": now,
                        },
                    )
                ]
                mock_summarize.reset_mock()
                scheduling.update_summary()
                mock_summarize.assert_called_once()
                prompt = mock_summarize.call_args.args[0]
                for marker in (
                    "CameraMarker",
                    "Sensitive prompt marker",
                    "Sensitive caption marker",
                ):
                    self.assertEqual(marker in prompt, included)
