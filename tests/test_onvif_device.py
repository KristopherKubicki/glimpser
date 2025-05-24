import unittest
import time
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.onvif_device import ONVIFDevice
from app.utils.camera_discovery import _probe_onvif


class TestONVIFDevice(unittest.TestCase):
    def test_probe_onvif_detects_device(self):
        device = ONVIFDevice(host="127.0.0.1", http_port=50100)
        device.start()
        time.sleep(0.1)
        cams = _probe_onvif(timeout=1, host="127.0.0.1", port=3702)
        device.stop()
        self.assertTrue(any(cam["ip"] == "127.0.0.1" for cam in cams))


if __name__ == "__main__":
    unittest.main()
