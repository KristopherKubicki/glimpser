import unittest
from unittest.mock import patch

from app.utils import scheduling


class TestBaselineUpdate(unittest.TestCase):
    @patch("app.utils.scheduling.chatgpt_compare", return_value="desc")
    @patch("app.utils.scheduling.save_template")
    @patch("app.utils.scheduling.get_template", return_value={"name": "cam1"})
    @patch("app.utils.scheduling.get_screenshots_for_template")
    @patch(
        "app.utils.scheduling.get_templates", return_value={"cam1": {"name": "cam1"}}
    )
    def test_update_baselines(
        self, mock_templates, mock_shots, mock_get, mock_save, mock_compare
    ):
        mock_shots.return_value = [f"cam1_{i}.png" for i in range(12)]

        scheduling.update_baselines()

        mock_compare.assert_called_once()
        self.assertEqual(mock_save.call_count, 1)


class TestScheduleBaselineUpdates(unittest.TestCase):
    @patch("app.utils.scheduling.scheduler.add_job")
    def test_schedule_baseline_updates(self, mock_add):
        scheduling.schedule_baseline_updates()
        mock_add.assert_called_once()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
