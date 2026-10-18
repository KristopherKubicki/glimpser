from __future__ import annotations

import importlib
import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
from PIL import Image

from app import routes
from app.utils.sms_media import (
    InvalidSmsMediaRequest,
    render_sms_gif,
)
from app.utils.sms_media_storage import publish_sms_media


class DummyHttpResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return b""


class TestSmsMedia(unittest.TestCase):
    def _write_frame(self, directory: Path, name: str, color: tuple[int, int, int]):
        path = directory / name
        image = Image.new("RGB", (960, 540), color)
        image.save(path, "PNG")
        now = time.time()
        os.utime(path, (now, now))
        return path

    def _write_gradient_frame(self, directory: Path, name: str):
        path = directory / name
        image = Image.new("RGB", (960, 540))
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                pixels[x, y] = (x % 256, y % 256, (x + y) % 256)
        image.save(path, "PNG")
        now = time.time()
        os.utime(path, (now, now))
        return path

    def test_render_sms_gif_stamps_and_fits_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            camera_dir = Path(temp_dir) / "FrontDoor"
            camera_dir.mkdir()
            self._write_frame(camera_dir, "FrontDoor_001.png", (10, 40, 70))
            self._write_frame(camera_dir, "FrontDoor_002.png", (30, 80, 120))
            self._write_frame(camera_dir, "FrontDoor_003.png", (70, 120, 170))

            asset = render_sms_gif(
                "FrontDoor",
                temp_dir,
                long_edge=480,
                max_bytes=400_000,
                frames=3,
            )

            self.assertEqual(asset.content_type, "image/gif")
            self.assertLessEqual(asset.bytes, 400_000)
            self.assertEqual(asset.frames, 3)
            self.assertTrue(asset.body.startswith(b"GIF"))
            self.assertIn("stamped", asset.transform)

    def test_render_sms_gif_uses_slow_multiframe_timing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            camera_dir = Path(temp_dir) / "FrontDoor"
            camera_dir.mkdir()
            self._write_frame(camera_dir, "FrontDoor_001.png", (10, 40, 70))
            self._write_frame(camera_dir, "FrontDoor_002.png", (30, 80, 120))
            self._write_frame(camera_dir, "FrontDoor_003.png", (70, 120, 170))

            asset = render_sms_gif(
                "FrontDoor",
                temp_dir,
                long_edge=480,
                max_bytes=400_000,
                frames=3,
                frame_duration_ms=500,
            )

            with Image.open(io.BytesIO(asset.body)) as gif:
                self.assertEqual(gif.n_frames, 3)
                gif.seek(0)
                first_duration = gif.info["duration"]
                gif.seek(1)
                middle_duration = gif.info["duration"]
                gif.seek(2)
                last_duration = gif.info["duration"]

            self.assertGreater(first_duration, middle_duration)
            self.assertGreater(last_duration, middle_duration)
            self.assertIn("slow_stamped", asset.transform)

    def test_render_sms_gif_does_not_synthesize_zoom_motion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            camera_dir = Path(temp_dir) / "FrontDoor"
            camera_dir.mkdir()
            self._write_gradient_frame(camera_dir, "FrontDoor_001.png")

            asset = render_sms_gif(
                "FrontDoor",
                temp_dir,
                long_edge=480,
                max_bytes=400_000,
                frames=3,
            )

            samples = []
            with Image.open(io.BytesIO(asset.body)) as gif:
                for frame_index in range(gif.n_frames):
                    gif.seek(frame_index)
                    frame = gif.convert("RGB")
                    samples.append(
                        frame.getpixel((frame.width // 3, frame.height // 3))
                    )

            self.assertEqual(samples[0], samples[1])
            self.assertEqual(samples[1], samples[2])

    def test_render_sms_gif_rejects_invalid_camera_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(InvalidSmsMediaRequest):
                render_sms_gif("../FrontDoor", temp_dir)

    def test_sms_media_route_returns_metadata_and_gif(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            camera_dir = Path(temp_dir) / "FrontDoor"
            camera_dir.mkdir()
            self._write_frame(camera_dir, "FrontDoor_001.png", (20, 60, 90))
            self._write_frame(camera_dir, "FrontDoor_002.png", (40, 90, 130))

            importlib.reload(routes)
            app = Flask(__name__)
            app.config["SECRET_KEY"] = "test"
            with (
                patch("app.routes.SCREENSHOT_DIRECTORY", temp_dir),
                patch("app.routes.API_KEY", "test-key"),
                patch("app.routes.config.SKIP_LOGIN_SUBNETS", []),
            ):
                routes.init_routes(app)
                client = app.test_client()

                metadata = client.get(
                    "/api/sms-media/v1/render"
                    "?camera=FrontDoor&metadata=1&frames=2&long_edge=480",
                    headers={"X-API-Key": "test-key"},
                )
                self.assertEqual(metadata.status_code, 200)
                payload = metadata.get_json()
                self.assertEqual(payload["camera"], "FrontDoor")
                self.assertEqual(payload["content_type"], "image/gif")
                self.assertEqual(payload["frames"], 2)
                self.assertIn("stamped", payload["transform"])

                gif = client.get(
                    "/api/sms-media/v1/render?camera=FrontDoor&frames=2&long_edge=480",
                    headers={"X-API-Key": "test-key"},
                )
                self.assertEqual(gif.status_code, 200)
                self.assertEqual(gif.mimetype, "image/gif")
                self.assertTrue(gif.data.startswith(b"GIF"))
                self.assertEqual(gif.headers["X-Glimpser-Camera"], "FrontDoor")

    def test_publish_sms_media_returns_presigned_url(self):
        upload = Mock(return_value=DummyHttpResponse())
        with (
            patch.dict(os.environ, self._storage_env(), clear=False),
            patch("app.utils.sms_media_storage.urllib.request.urlopen", upload),
        ):
            published = publish_sms_media(
                camera="FrontDoor",
                body=b"GIF89a-test",
                content_type="image/gif",
                extension="gif",
            )

        self.assertTrue(published.key.startswith("twilio-snapshots/FrontDoor/"))
        self.assertIn("X-Amz-Signature=", published.media_url)
        self.assertIn("X-Amz-Expires=300", published.media_url)
        request = upload.call_args.args[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.headers["Content-type"], "image/gif")

    def test_sms_media_route_publish_returns_media_url(self):
        upload = Mock(return_value=DummyHttpResponse())
        with tempfile.TemporaryDirectory() as temp_dir:
            camera_dir = Path(temp_dir) / "FrontDoor"
            camera_dir.mkdir()
            self._write_frame(camera_dir, "FrontDoor_001.png", (20, 60, 90))
            self._write_frame(camera_dir, "FrontDoor_002.png", (40, 90, 130))

            importlib.reload(routes)
            app = Flask(__name__)
            app.config["SECRET_KEY"] = "test"
            with (
                patch("app.routes.SCREENSHOT_DIRECTORY", temp_dir),
                patch("app.routes.API_KEY", "test-key"),
                patch("app.routes.config.SKIP_LOGIN_SUBNETS", []),
                patch.dict(os.environ, self._storage_env(), clear=False),
                patch("app.utils.sms_media_storage.urllib.request.urlopen", upload),
            ):
                routes.init_routes(app)
                client = app.test_client()
                response = client.get(
                    "/api/sms-media/v1/render"
                    "?camera=FrontDoor&publish=1&frames=2&long_edge=480",
                    headers={"X-API-Key": "test-key"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["camera"], "FrontDoor")
        self.assertEqual(payload["content_type"], "image/gif")
        self.assertIn("media_url", payload)
        self.assertIn("X-Amz-Signature=", payload["media_url"])
        self.assertTrue(payload["key"].startswith("twilio-snapshots/FrontDoor/"))

    def _storage_env(self):
        return {
            "GLIMPSER_SMS_MEDIA_ENDPOINT_URL": "https://s3.us-east-2.amazonaws.com",
            "GLIMPSER_SMS_MEDIA_BUCKET": "test-bucket",
            "GLIMPSER_SMS_MEDIA_REGION": "us-east-2",
            "GLIMPSER_SMS_MEDIA_ACCESS_KEY_ID": "test-access",
            "GLIMPSER_SMS_MEDIA_SECRET_ACCESS_KEY": "test-secret",
            "GLIMPSER_SMS_MEDIA_EXPIRES_SECONDS": "300",
            "GLIMPSER_SMS_MEDIA_KEY_PREFIX": "twilio-snapshots",
        }


if __name__ == "__main__":
    unittest.main()
