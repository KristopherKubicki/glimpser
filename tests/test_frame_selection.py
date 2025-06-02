import unittest
import tempfile
import os
import sys
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.scheduling import select_comparison_frames


class TestSelectComparisonFrames(unittest.TestCase):
    def test_selects_existing_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            Image.new("RGB", (1, 1)).save(os.path.join(tmp, "reference.png"))
            Image.new("RGB", (1, 1)).save(os.path.join(tmp, "prev_motion.png"))
            latest = os.path.join(tmp, "latest.png")
            Image.new("RGB", (1, 1)).save(latest)

            frames = select_comparison_frames(tmp, latest)
            self.assertEqual(
                frames,
                [
                    os.path.join(tmp, "reference.png"),
                    os.path.join(tmp, "prev_motion.png"),
                    latest,
                ],
            )

    def test_fallback_to_last_motion(self):
        with tempfile.TemporaryDirectory() as tmp:
            Image.new("RGB", (1, 1)).save(os.path.join(tmp, "last_motion.png"))
            latest = os.path.join(tmp, "new.png")
            Image.new("RGB", (1, 1)).save(latest)

            frames = select_comparison_frames(tmp, latest)
            self.assertIn(os.path.join(tmp, "last_motion.png"), frames)
            self.assertIn(latest, frames)
            self.assertEqual(len(frames), 2)


if __name__ == "__main__":
    unittest.main()
