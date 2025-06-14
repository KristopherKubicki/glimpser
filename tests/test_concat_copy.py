import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.routes as routes


class TestConcatCopy(unittest.TestCase):
    def test_pad_uses_first_frame_overlay(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "clip.mp4"
            part = Path(tmpdir) / "final_0.mp4"
            part.touch()
            parts = [part]

            calls = []

            def fake_run(cmd, *args, **kwargs):
                calls.append(cmd)
                if cmd:
                    last = cmd[-1]
                    if isinstance(last, (str, Path)) and str(last).endswith(".mp4"):
                        Path(str(last)).touch()
                return None

            with (
                patch.object(routes, "_duration", return_value=1),
                patch.object(
                    routes,
                    "_probe",
                    side_effect=lambda p, k: {
                        "width": "640",
                        "height": "360",
                        "r_frame_rate": "30/1",
                    }[k],
                ),
                patch("subprocess.run", side_effect=fake_run),
            ):
                self.assertTrue(routes._concat_copy(out, parts, clip_len=2))

            overlay_cmd = next(
                (c for c in calls if "color=c=black@0.9" in " ".join(map(str, c))),
                None,
            )
            self.assertIsNotNone(overlay_cmd)

    def test_trim_uses_start_offset(self):
        """Ensure trimming seeks forward when clips exceed the limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "clip.mp4"
            p1 = Path(tmpdir) / "final_1.mp4"
            p2 = Path(tmpdir) / "final_2.mp4"
            p1.touch()
            p2.touch()
            parts = [p1, p2]

            calls = []

            def fake_run(cmd, *args, **kwargs):
                calls.append(cmd)
                if cmd:
                    last = cmd[-1]
                    if isinstance(last, (str, Path)) and str(last).endswith(".mp4"):
                        Path(str(last)).touch()
                return None

            with (
                patch.object(routes, "_duration", return_value=2),
                patch("subprocess.run", side_effect=fake_run),
            ):
                self.assertTrue(routes._concat_copy(out, parts, clip_len=3))

            concat_cmd = calls[-1]
            ss_idx = concat_cmd.index("-ss")
            t_idx = concat_cmd.index("-t")
            self.assertLess(ss_idx, t_idx)
            self.assertEqual(concat_cmd[ss_idx + 1], "1.000")


if __name__ == "__main__":
    unittest.main()
