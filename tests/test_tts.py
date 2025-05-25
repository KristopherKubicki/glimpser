import os
import sys
import tempfile
import unittest
import importlib
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestGenerateTTS(unittest.TestCase):
    def test_generate_creates_audio(self):
        engine = MagicMock()

        def fake_save_to_file(text, path):
            with open(path, "wb") as f:
                f.write(b"data")

        engine.save_to_file.side_effect = fake_save_to_file

        with patch.dict(
            "sys.modules",
            {"pyttsx3": MagicMock(init=MagicMock(return_value=engine))},
        ):
            import app.utils.tts as tts

            importlib.reload(tts)

            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "out.mp3")
                tts.generate_tts("hello", out)
                self.assertTrue(os.path.exists(out))
                self.assertGreater(os.path.getsize(out), 0)

        engine.runAndWait.assert_called_once()
        engine.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
