import unittest
import socket
import os
import sys
from ipaddress import ip_network
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils import camera_discovery


class TestCameraDiscovery(unittest.TestCase):
    def _mock_interfaces(self):
        snicaddr = camera_discovery.psutil._common.snicaddr
        return {
            "eth0": [
                snicaddr(
                    family=socket.AF_INET,
                    address="192.168.1.5",
                    netmask="255.255.255.252",
                    broadcast="192.168.1.7",
                    ptp=None,
                )
            ],
            "wlan0": [
                snicaddr(
                    family=socket.AF_INET,
                    address="10.0.0.5",
                    netmask="255.255.255.252",
                    broadcast="10.0.0.7",
                    ptp=None,
                )
            ],
        }

    def _port_open_side_effect(self, ip, port, timeout=1):
        return (ip, port) in {
            ("192.168.1.6", 554),
            ("10.0.0.6", 8554),
            ("192.168.1.6", 1935),
            ("192.168.1.6", 5060),
            ("10.0.0.6", 5349),
        }

    @patch("app.utils.camera_discovery.glob.glob")
    def test_local_video_devices(self, mock_glob):
        mock_glob.return_value = ["/dev/video0", "/dev/video1"]
        result = camera_discovery._local_video_devices()
        expected = [
            {"ip": "/dev/video0", "protocol": "local", "port": 0, "info": {}},
            {"ip": "/dev/video1", "protocol": "local", "port": 0, "info": {}},
        ]
        self.assertEqual(result, expected)

    @patch("app.utils.camera_discovery.psutil.net_if_addrs")
    def test_local_subnets(self, mock_addrs):
        mock_addrs.return_value = self._mock_interfaces()
        result = camera_discovery._local_subnets()
        expected = {
            ip_network("192.168.1.5/255.255.255.252", strict=False),
            ip_network("10.0.0.5/255.255.255.252", strict=False),
        }
        self.assertEqual(set(result), expected)

    @patch("app.utils.camera_discovery.is_port_open")
    def test_scan_rtsp_ports(self, mock_port_open):
        mock_port_open.side_effect = self._port_open_side_effect
        subnets = [
            ip_network("192.168.1.5/255.255.255.252", strict=False),
            ip_network("10.0.0.5/255.255.255.252", strict=False),
        ]
        result = camera_discovery._scan_rtsp_ports(subnets)
        expected = [
            {"ip": "192.168.1.6", "protocol": "rtsp", "port": 554, "info": {}},
            {"ip": "10.0.0.6", "protocol": "rtsp", "port": 8554, "info": {}},
        ]
        self.assertEqual(result, expected)

    @patch("app.utils.camera_discovery.is_port_open")
    def test_scan_rtmp_ports(self, mock_port_open):
        mock_port_open.side_effect = self._port_open_side_effect
        subnets = [
            ip_network("192.168.1.5/255.255.255.252", strict=False),
            ip_network("10.0.0.5/255.255.255.252", strict=False),
        ]
        result = camera_discovery._scan_rtmp_ports(subnets)
        expected = [
            {"ip": "192.168.1.6", "protocol": "rtmp", "port": 1935, "info": {}},
        ]
        self.assertEqual(result, expected)

    @patch("app.utils.camera_discovery.is_port_open")
    def test_scan_sip_ports(self, mock_port_open):
        mock_port_open.side_effect = self._port_open_side_effect
        subnets = [
            ip_network("192.168.1.5/255.255.255.252", strict=False),
            ip_network("10.0.0.5/255.255.255.252", strict=False),
        ]
        result = camera_discovery._scan_sip_ports(subnets)
        expected = [
            {"ip": "192.168.1.6", "protocol": "sip", "port": 5060, "info": {}},
        ]
        self.assertEqual(result, expected)

    @patch("app.utils.camera_discovery.is_port_open")
    def test_scan_webrtc_ports(self, mock_port_open):
        mock_port_open.side_effect = self._port_open_side_effect
        subnets = [
            ip_network("192.168.1.5/255.255.255.252", strict=False),
            ip_network("10.0.0.5/255.255.255.252", strict=False),
        ]
        result = camera_discovery._scan_webrtc_ports(subnets)
        expected = [
            {"ip": "10.0.0.6", "protocol": "webrtc", "port": 5349, "info": {}},
        ]
        self.assertEqual(result, expected)

    @patch("app.utils.camera_discovery._probe_mdns")
    @patch("app.utils.camera_discovery._probe_onvif")
    @patch("app.utils.camera_discovery.is_port_open")
    @patch("app.utils.camera_discovery.psutil.net_if_addrs")
    def test_discover_cameras_merge(
        self, mock_addrs, mock_port_open, mock_onvif, mock_mdns
    ):
        mock_addrs.return_value = self._mock_interfaces()
        mock_port_open.side_effect = self._port_open_side_effect
        mock_onvif.return_value = [
            {"ip": "192.168.1.6", "protocol": "onvif", "port": 80, "info": {}},
            {
                "ip": "192.168.1.6",
                "protocol": "onvif",
                "port": 80,
                "info": {},
            },  # duplicate
        ]
        mock_mdns.return_value = [
            {"ip": "192.168.1.7", "protocol": "mdns", "port": 8080, "info": {}}
        ]
        result = camera_discovery.discover_cameras()
        expected = [
            {"ip": "192.168.1.6", "protocol": "onvif", "port": 80, "info": {}},
            {"ip": "192.168.1.6", "protocol": "rtsp", "port": 554, "info": {}},
            {"ip": "10.0.0.6", "protocol": "rtsp", "port": 8554, "info": {}},
            {"ip": "192.168.1.6", "protocol": "rtmp", "port": 1935, "info": {}},
            {"ip": "192.168.1.6", "protocol": "sip", "port": 5060, "info": {}},
            {"ip": "10.0.0.6", "protocol": "webrtc", "port": 5349, "info": {}},
            {"ip": "192.168.1.7", "protocol": "mdns", "port": 8080, "info": {}},
            {
                "ip": "127.0.0.1",
                "protocol": "http",
                "port": 8082,
                "info": {"name": "System Status"},
            },
        ]
        # convert to set of tuples for comparison ignoring order
        self.assertEqual(
            {(c["ip"], c["protocol"], c["port"]) for c in result},
            {(c["ip"], c["protocol"], c["port"]) for c in expected},
        )


if __name__ == "__main__":
    unittest.main()
