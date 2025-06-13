import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.utils.scheduling as scheduling


class TestClipModelSetting(unittest.TestCase):
    def test_custom_onnx_clip_model_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            cam_dir = os.path.join(tmp, "cam1")
            os.makedirs(cam_dir)
            Image.new("RGB", (10, 10)).save(
                os.path.join(cam_dir, "cam1_20240101000000.png")
            )

            template = {
                "name": "cam1",
                "object_filter": "dog",
                "object_confidence": 0,
                "last_caption": "",
                "last_motion_caption": "",
                "notes": "",
                "frequency": 30,
                "motion": 0,
            }

            class DummySession:
                calls = []

                def __init__(self, path):
                    DummySession.calls.append(path)

                def run(self, *_args, **_kwargs):
                    return [np.array([[1.0]])]

            class DummyProcessor:
                calls = []

                @classmethod
                def from_pretrained(cls, name):
                    cls.calls.append(name)
                    return cls()

                def __call__(self, text, images, return_tensors=None, padding=None):
                    return {
                        "input_ids": np.array([[0]]),
                        "attention_mask": np.array([[1]]),
                        "pixel_values": np.zeros((1, 3, 32, 32)),
                    }

            with (
                patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", tmp),
                patch("app.utils.scheduling.CLIP_MODEL_NAME", "custom-model"),
                patch("app.utils.scheduling.CLIP_MODEL_PATH", "custom-model"),
                patch("app.utils.scheduling.capture_or_download", return_value=True),
                patch("app.utils.scheduling.add_timestamp"),
                patch("app.utils.scheduling.remove_background"),
                patch("app.utils.scheduling.add_motion_and_caption"),
                patch("app.utils.scheduling.save_template"),
                patch("app.utils.scheduling.send_http_callback"),
                patch("app.utils.scheduling.chatgpt_compare", return_value="caption"),
                patch("app.utils.scheduling.is_mostly_blank", return_value=False),
                patch("app.utils.scheduling.get_template", return_value=template),
                patch("os.symlink"),
                patch("os.rename"),
                patch("os.unlink"),
                patch(
                    "app.utils.scheduling.ort",
                    types.SimpleNamespace(InferenceSession=DummySession),
                ),
                patch(
                    "app.utils.scheduling.CLIPProcessor", DummyProcessor
                ) as mock_processor_class,
            ):
                scheduling.clip_session = None
                scheduling.clip_processor = None
                scheduling.update_camera("cam1", template)
                self.assertEqual(DummySession.calls, ["custom-model"])
                self.assertEqual(DummyProcessor.calls, ["custom-model"])

    def test_skips_when_onnx_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cam_dir = os.path.join(tmp, "cam1")
            os.makedirs(cam_dir)
            Image.new("RGB", (10, 10)).save(
                os.path.join(cam_dir, "cam1_20240101000000.png")
            )

            template = {
                "name": "cam1",
                "object_filter": "dog",
                "object_confidence": 0,
                "last_caption": "",
                "last_motion_caption": "",
                "notes": "",
                "frequency": 30,
                "motion": 0,
            }

            class DummyProcessor:
                called = False

                @classmethod
                def from_pretrained(cls, name):
                    cls.called = True
                    return cls()

            with (
                patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", tmp),
                patch("app.utils.scheduling.CLIP_MODEL_NAME", "custom-model"),
                patch("app.utils.scheduling.capture_or_download", return_value=True),
                patch("app.utils.scheduling.add_timestamp"),
                patch("app.utils.scheduling.remove_background"),
                patch("app.utils.scheduling.add_motion_and_caption"),
                patch("app.utils.scheduling.save_template"),
                patch("app.utils.scheduling.send_http_callback"),
                patch("app.utils.scheduling.chatgpt_compare", return_value="caption"),
                patch("app.utils.scheduling.is_mostly_blank", return_value=False),
                patch("app.utils.scheduling.get_template", return_value=template),
                patch("os.symlink"),
                patch("os.rename"),
                patch("os.unlink"),
                patch("app.utils.scheduling.ort", None),
                patch("app.utils.scheduling.CLIPProcessor", DummyProcessor),
            ):
                scheduling.clip_session = None
                scheduling.clip_processor = None
                scheduling.update_camera("cam1", template)
                self.assertFalse(DummyProcessor.called)


if __name__ == "__main__":
    unittest.main()
