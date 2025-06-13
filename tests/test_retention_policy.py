# Integration tests for retention_policy cleanup logic

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch

import app.utils.retention_policy as retention_policy
from app.utils.retention_policy import (
    cleanup_clips,
    delete_old_files,
    get_files_sorted_by_creation_time,
    retention_cleanup,
)


class TestRetentionPolicy(unittest.TestCase):

    def test_delete_old_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create dummy files in sequence so creation times increase
            file_paths = []
            for i in range(5):
                file_path = os.path.join(temp_dir, f"file{i}.txt")
                with open(file_path, "w") as f:
                    f.write("Some content")
                file_paths.append(file_path)
                time.sleep(0.01)  # ensure distinct timestamps

            # Run the delete function
            delete_old_files(file_paths, max_age=0, max_size=0, minimum=2)

            # Check that only the two newest files remain
            remaining_files = os.listdir(temp_dir)
            self.assertEqual(set(remaining_files), {"file3.txt", "file4.txt"})

    def test_delete_old_files_removes_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = os.path.join(temp_dir, "old")
            os.makedirs(dir_path)

            delete_old_files([dir_path], max_age=0, max_size=0, minimum=0)

            self.assertFalse(os.path.exists(dir_path))

    def test_get_files_sorted_by_creation_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_paths = []
            for name in ["a.txt", "b.txt", "c.txt"]:
                path = os.path.join(temp_dir, name)
                with open(path, "w"):
                    pass
                file_paths.append(path)
                time.sleep(0.01)

            # Add a symlink which should be ignored
            os.symlink(file_paths[0], os.path.join(temp_dir, "link"))

            result = get_files_sorted_by_creation_time(temp_dir)
            # Symlinks are excluded and files are sorted oldest -> newest
            self.assertEqual(result, file_paths)

    @patch("app.utils.retention_policy.os.listdir")
    @patch("app.utils.retention_policy.get_files_sorted_by_creation_time")
    @patch("app.utils.retention_policy.delete_old_files")
    def test_retention_cleanup_invokes_deletion(
        self, mock_delete, mock_get_files, mock_listdir
    ):
        mock_listdir.side_effect = [["cam1"], ["cam1"], ["cam1"]]
        mock_get_files.return_value = ["f1", "f2"]

        retention_cleanup()

        self.assertEqual(mock_get_files.call_count, 2)
        mock_delete.assert_called_with(
            ["f1", "f2"],
            retention_policy.MAX_COMPRESSED_VIDEO_AGE,
            retention_policy.MAX_RAW_DATA_SIZE,
        )
        self.assertEqual(mock_delete.call_count, 2)

    def test_retention_cleanup_temp_dirs(self):
        with (
            tempfile.TemporaryDirectory() as video_dir,
            tempfile.TemporaryDirectory() as shot_dir,
        ):
            os.makedirs(os.path.join(video_dir, "cam1"))
            os.makedirs(os.path.join(shot_dir, "cam1"))
            for root in (video_dir, shot_dir):
                cam = os.path.join(root, "cam1")
                for i in range(12):
                    with open(os.path.join(cam, f"file{i}.txt"), "w") as f:
                        f.write("data")
                    time.sleep(0.01)

            with (
                patch.object(retention_policy, "VIDEO_DIRECTORY", video_dir),
                patch.object(retention_policy, "SCREENSHOT_DIRECTORY", shot_dir),
                patch.object(retention_policy, "MAX_COMPRESSED_VIDEO_AGE", 0),
                patch.object(retention_policy, "MAX_RAW_DATA_SIZE", 0),
            ):
                retention_cleanup()

            self.assertEqual(
                len(os.listdir(os.path.join(video_dir, "cam1"))),
                10,
            )
            self.assertEqual(
                len(os.listdir(os.path.join(shot_dir, "cam1"))),
                10,
            )

    def test_cleanup_clips_removes_expired(self):
        with tempfile.TemporaryDirectory() as clip_dir:
            cam_dir = os.path.join(clip_dir, "cam1")
            os.makedirs(cam_dir)
            clip = os.path.join(clip_dir, "cam1.mp4")
            with open(clip, "w"):
                pass
            old = time.time() - 600
            os.utime(clip, (old, old))

            with (
                patch.object(retention_policy, "CLIPS_DIRECTORY", clip_dir),
                patch(
                    "app.utils.retention_policy.check_user_activity",
                    return_value=False,
                ),
            ):
                cleanup_clips(max_age_minutes=5)

            self.assertFalse(os.path.exists(clip))

    def test_cleanup_clips_keeps_recent(self):
        with tempfile.TemporaryDirectory() as clip_dir:
            cam_dir = os.path.join(clip_dir, "cam1")
            os.makedirs(cam_dir)
            clip = os.path.join(clip_dir, "cam1.mp4")
            with open(clip, "w"):
                pass
            with (
                patch.object(retention_policy, "CLIPS_DIRECTORY", clip_dir),
                patch(
                    "app.utils.retention_policy.check_user_activity",
                    return_value=False,
                ),
            ):
                cleanup_clips(max_age_minutes=5)

            self.assertTrue(os.path.exists(clip))


if __name__ == "__main__":
    unittest.main()
