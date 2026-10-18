import math
import unittest
from unittest.mock import patch

from scripts.backfill_stale_captions import (
    caption_lag_hours,
    select_stale_caption_candidates,
    wait_for_cpu_capacity,
)


class TestBackfillStaleCaptions(unittest.TestCase):
    def test_caption_lag_hours(self):
        lag = caption_lag_hours(
            {
                "last_screenshot_time": "2026-05-04 12:00:00",
                "last_caption_time": "2026-05-04 09:30:00",
            }
        )

        self.assertEqual(lag, 2.5)

    def test_caption_lag_hours_infinite_when_caption_time_missing(self):
        lag = caption_lag_hours(
            {
                "last_screenshot_time": "2026-05-04 12:00:00",
                "last_caption_time": "",
            }
        )

        self.assertTrue(math.isinf(lag))

    def test_select_candidates_filters_groups_and_failed_templates(self):
        templates = {
            "SiteOneFresh": {
                "groups": "site-one",
                "last_caption": "caption",
                "last_screenshot_time": "2026-05-04 12:00:00",
                "last_caption_time": "2026-05-04 11:00:00",
                "frequency": 30,
            },
            "SiteOneStale": {
                "groups": "site-one",
                "last_caption": "caption",
                "last_screenshot_time": "2026-05-04 12:00:00",
                "last_caption_time": "2026-05-03 00:00:00",
                "frequency": 30,
            },
            "ArchiveStale": {
                "groups": "archive,site-one",
                "last_caption": "caption",
                "last_screenshot_time": "2026-05-04 12:00:00",
                "last_caption_time": "2026-05-03 00:00:00",
                "frequency": 30,
            },
            "FailedStale": {
                "groups": "site-one",
                "capture_failed": True,
                "last_caption": "caption",
                "last_screenshot_time": "2026-05-04 12:00:00",
                "last_caption_time": "2026-05-03 00:00:00",
                "frequency": 30,
            },
            "SiteTwoStale": {
                "groups": "site-two",
                "last_caption": "caption",
                "last_screenshot_time": "2026-05-04 12:00:00",
                "last_caption_time": "2026-05-03 00:00:00",
                "frequency": 30,
            },
        }

        candidates = select_stale_caption_candidates(
            templates,
            include_groups={"site-one"},
            min_lag_hours=24,
        )

        self.assertEqual([candidate.name for candidate in candidates], ["SiteOneStale"])

    def test_wait_for_cpu_capacity_stops_after_attempts(self):
        with patch(
            "scripts.backfill_stale_captions.psutil.cpu_percent",
            side_effect=[95.0, 96.0],
        ):
            self.assertFalse(
                wait_for_cpu_capacity(
                    max_cpu_percent=75.0,
                    wait_seconds=0,
                    attempts=2,
                )
            )

    def test_wait_for_cpu_capacity_accepts_available_cpu(self):
        with patch(
            "scripts.backfill_stale_captions.psutil.cpu_percent",
            return_value=30.0,
        ):
            self.assertTrue(
                wait_for_cpu_capacity(
                    max_cpu_percent=75.0,
                    wait_seconds=0,
                    attempts=2,
                )
            )


if __name__ == "__main__":
    unittest.main()


def test_expected_offline_is_not_selected_for_caption_backfill():
    template = {
        "groups": "expected-offline",
        "last_caption": "old caption",
        "last_screenshot_time": "2026-05-04 12:00:00",
        "last_caption_time": "2026-05-01 12:00:00",
        "frequency": 30,
    }
    with patch(
        "scripts.backfill_stale_captions._caption_refresh_due", return_value=True
    ):
        assert select_stale_caption_candidates({"ExampleDetached": template}) == []
        template["groups"] = "active"
        assert len(select_stale_caption_candidates({"ExampleActive": template})) == 1
