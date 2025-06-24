import socket
import unittest
from collections import namedtuple
from unittest.mock import patch

from app.utils import settings_tooltips
from app.utils.template_manager import is_snapshot_url
from app.utils.validators import is_public_url


class TestIsPublicURL(unittest.TestCase):
    def test_public(self):
        self.assertTrue(is_public_url("http://example.com"))

    def test_private_ip(self):
        self.assertFalse(is_public_url("http://192.168.0.1"))

    def test_localhost(self):
        self.assertFalse(is_public_url("http://localhost"))

    def test_invalid(self):
        self.assertFalse(is_public_url("not a url"))


class TestIsSnapshotURL(unittest.TestCase):
    def test_snapshot_extensions(self):
        for url in [
            "http://cam/image.jpg",
            "http://cam/image.jpeg",
            "http://cam/image.PNG",
        ]:
            with self.subTest(url=url):
                self.assertTrue(is_snapshot_url(url))

    def test_snapshot_keywords(self):
        for url in [
            "http://cam/snapshot",
            "http://cam/picture.cgi",
        ]:
            with self.subTest(url=url):
                self.assertTrue(is_snapshot_url(url))

    def test_not_snapshot(self):
        self.assertFalse(is_snapshot_url("http://cam/stream.m3u8"))
        self.assertFalse(is_snapshot_url(""))


class TestHostChoices(unittest.TestCase):
    def test_collected_addresses(self):
        Snic = namedtuple("snicaddr", "family address netmask broadcast ptp")
        fake_addrs = {
            "eth0": [Snic(socket.AF_INET, "10.0.0.5", None, None, None)],
            "lo": [Snic(socket.AF_INET, "127.0.0.1", None, None, None)],
        }
        with patch(
            "app.utils.settings_tooltips.psutil.net_if_addrs",
            return_value=fake_addrs,
        ):
            choices = settings_tooltips._host_choices()
        self.assertIn("10.0.0.5", choices)
        self.assertIn("0.0.0.0", choices)
        self.assertIn("127.0.0.1", choices)


if __name__ == "__main__":
    unittest.main()
