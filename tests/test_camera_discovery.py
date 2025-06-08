import unittest
import socket
import os
import sys
import tempfile
from pathlib import Path
from ipaddress import ip_network
from unittest.mock import patch
from types import SimpleNamespace

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
            "lo": [
                snicaddr(
                    family=socket.AF_INET,
                    address="127.0.0.1",
                    netmask="255.0.0.0",
                    broadcast=None,
                    ptp=None,
                )
            ],
            "link0": [
                snicaddr(
                    family=socket.AF_INET,
                    address="169.254.1.1",
                    netmask="255.255.0.0",
                    broadcast=None,
                    ptp=None,
                )
            ],
        }

    def _mock_stats(self):
        snicstats = camera_discovery.psutil._common.snicstats
        # all interfaces are up to ensure filtering is based on address type
        return {
            "eth0": snicstats(isup=True, duplex=0, speed=0, mtu=1500, flags=0),
            "wlan0": snicstats(isup=True, duplex=0, speed=0, mtu=1500, flags=0),
            "lo": snicstats(isup=True, duplex=0, speed=0, mtu=65536, flags=0),
            "link0": snicstats(isup=True, duplex=0, speed=0, mtu=1500, flags=0),
        }

    def _port_open_side_effect(self, ip, port, timeout=1):
        return (ip, port) in {
            ("192.168.1.6", 554),
            ("10.0.0.6", 8554),
            ("192.168.1.6", 1935),
            ("192.168.1.6", 5060),
            ("10.0.0.6", 5349),
            ("192.168.1.6", 161),
            ("192.168.1.6", 80),
            ("10.0.0.6", 8080),
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

    @patch("app.utils.camera_discovery.psutil.net_if_stats")
    @patch("app.utils.camera_discovery.psutil.net_if_addrs")
    def test_local_subnets(self, mock_addrs, mock_stats):
        mock_addrs.return_value = self._mock_interfaces()
        mock_stats.return_value = self._mock_stats()
        result = camera_discovery._local_subnets()
        expected = {
            ip_network("192.168.1.5/255.255.255.252", strict=False),
            ip_network("10.0.0.5/255.255.255.252", strict=False),
        }
        self.assertEqual(set(result), expected)

    def test_get_discovery_stages_has_trace(self):
        stages = camera_discovery.get_discovery_stages()
        self.assertIn("trace", stages)
        self.assertEqual(stages[-1], "trace")

    @patch("app.utils.camera_discovery._fetch_sdp")
    @patch("app.utils.camera_discovery.is_port_open")
    def test_scan_rtsp_ports(self, mock_port_open, mock_fetch_sdp):
        mock_port_open.side_effect = self._port_open_side_effect
        mock_fetch_sdp.return_value = "v=0"  # simplified SDP
        subnets = [
            ip_network("192.168.1.5/255.255.255.252", strict=False),
            ip_network("10.0.0.5/255.255.255.252", strict=False),
        ]
        result = camera_discovery._scan_rtsp_ports(subnets)
        expected = [
            {
                "ip": "192.168.1.6",
                "protocol": "rtsp",
                "port": 554,
                "info": {"sdp": "v=0"},
            },
            {
                "ip": "10.0.0.6",
                "protocol": "rtsp",
                "port": 8554,
                "info": {"sdp": "v=0"},
            },
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

    @patch("app.utils.camera_discovery._fetch_snmp_sysname")
    @patch("app.utils.camera_discovery.is_port_open")
    def test_scan_snmp_ports(self, mock_port_open, mock_fetch_name):
        mock_port_open.side_effect = self._port_open_side_effect
        mock_fetch_name.return_value = "cam1"
        subnets = [
            ip_network("192.168.1.5/255.255.255.252", strict=False),
            ip_network("10.0.0.5/255.255.255.252", strict=False),
        ]
        result = camera_discovery._scan_snmp_ports(subnets)
        expected = [
            {
                "ip": "192.168.1.6",
                "protocol": "snmp",
                "port": 161,
                "info": {"name": "cam1"},
            },
        ]
        self.assertEqual(result, expected)

    @patch("app.utils.camera_discovery._trace_upstream", return_value="192.168.1.1")
    @patch("app.utils.camera_discovery._probe_ssdp")
    @patch("app.utils.camera_discovery._probe_mdns")
    @patch("app.utils.camera_discovery._probe_onvif")
    @patch("app.utils.camera_discovery.is_port_open")
    @patch("app.utils.camera_discovery._check_http_endpoint")
    @patch("app.utils.camera_discovery._fetch_snmp_sysname")
    @patch("app.utils.camera_discovery._fetch_sdp")
    @patch("app.utils.camera_discovery.psutil.net_if_addrs")
    @patch("app.utils.camera_discovery._local_video_devices", return_value=[])
    def test_discover_cameras_merge(
        self,
        mock_local_video_devices,
        mock_addrs,
        mock_fetch_sdp,
        mock_fetch_snmp,
        mock_check_http,
        mock_port_open,
        mock_onvif,
        mock_mdns,
        mock_ssdp,
        mock_trace,
    ):
        mock_addrs.return_value = self._mock_interfaces()
        mock_port_open.side_effect = self._port_open_side_effect
        mock_fetch_sdp.return_value = "v=0"
        mock_fetch_snmp.return_value = "cam1"
        mock_check_http.side_effect = lambda ip, port, path, timeout=1: (
            (ip, port, path)
            in {
                ("192.168.1.6", 80, "/snapshot.jpg"),
                ("10.0.0.6", 8080, "/index.m3u8"),
            }
        )
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
        mock_ssdp.return_value = [
            {"ip": "192.168.1.8", "protocol": "ssdp", "port": 80, "info": {}}
        ]
        result = camera_discovery.discover_cameras()
        expected = [
            {"ip": "192.168.1.6", "protocol": "onvif", "port": 80, "info": {}},
            {
                "ip": "192.168.1.6",
                "protocol": "rtsp",
                "port": 554,
                "info": {"sdp": "v=0"},
            },
            {
                "ip": "10.0.0.6",
                "protocol": "rtsp",
                "port": 8554,
                "info": {"sdp": "v=0"},
            },
            {"ip": "192.168.1.6", "protocol": "rtmp", "port": 1935, "info": {}},
            {"ip": "192.168.1.6", "protocol": "sip", "port": 5060, "info": {}},
            {"ip": "10.0.0.6", "protocol": "webrtc", "port": 5349, "info": {}},
            {
                "ip": "192.168.1.6",
                "protocol": "http",
                "port": 80,
                "info": {"path": "/snapshot.jpg"},
            },
            {
                "ip": "10.0.0.6",
                "protocol": "hls",
                "port": 8080,
                "info": {"path": "/index.m3u8"},
            },
            {
                "ip": "192.168.1.6",
                "protocol": "snmp",
                "port": 161,
                "info": {"name": "cam1"},
            },
            {"ip": "192.168.1.7", "protocol": "mdns", "port": 8080, "info": {}},
            {"ip": "192.168.1.8", "protocol": "ssdp", "port": 80, "info": {}},
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
        upstreams = [
            c["info"].get("upstream")
            for c in result
            if c["ip"] == "192.168.1.6" and c["protocol"] == "onvif"
        ]
        self.assertEqual(upstreams[0], "192.168.1.1")

    @patch("app.utils.camera_discovery._local_subnets", return_value=[])
    @patch("app.utils.camera_discovery._local_video_devices", return_value=[])
    @patch("app.utils.camera_discovery._scan_hls_streams", return_value=[])
    @patch("app.utils.camera_discovery._scan_http_endpoints", return_value=[])
    @patch("app.utils.camera_discovery._scan_snmp_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_webrtc_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_sip_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_rtmp_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_rtsp_ports", return_value=[])
    @patch("app.utils.camera_discovery._probe_ssdp", return_value=[])
    @patch("app.utils.camera_discovery._probe_mdns", return_value=[])
    @patch("app.utils.camera_discovery._probe_onvif")
    @patch("app.utils.camera_discovery._mac_manufacturer")
    @patch("app.utils.camera_discovery._mac_for_ip")
    @patch("app.utils.camera_discovery.is_port_open", return_value=False)
    @patch("app.utils.camera_discovery._trace_upstream", return_value=None)
    def test_progress_callback_includes_mac(
        self,
        mock_trace,
        mock_is_port_open,
        mock_mac,
        mock_vendor,
        mock_onvif,
        *_mocks,
    ):
        mock_onvif.return_value = [
            {"ip": "192.168.1.6", "protocol": "rtsp", "port": 554, "info": {}}
        ]
        mock_mac.return_value = "000c29aabbcc"
        mock_vendor.return_value = "VMware"

        seen = []

        def cb(stage, count, cams, *_):
            seen.extend(cams)

        camera_discovery.discover_cameras(progress_callback=cb)

        self.assertEqual(seen[0]["info"].get("mac"), "000c29aabbcc")
        self.assertEqual(seen[0]["info"].get("manufacturer"), "VMware")

    @patch("app.utils.camera_discovery.is_port_open")
    def test_detect_open_ports(self, mock_open):
        mock_open.side_effect = lambda ip, port, timeout=1: port in (80, 554)
        result = camera_discovery._detect_open_ports("192.168.1.6", [80, 443, 554])
        self.assertEqual(result, [80, 554])

    @patch("app.utils.camera_discovery.socket.create_connection")
    def test_fetch_http_banner(self, mock_conn):
        class FakeSock:
            resp = (
                b"HTTP/1.1 200 OK\r\n"
                b"Server: Cam/1.0\r\n"
                b'WWW-Authenticate: Basic realm="demo"\r\n\r\n'
                b"<html><title>Demo Cam</title></html>"
            )

            def __init__(self):
                self._sent = False
                self._idx = 0

            def sendall(self, data):
                self._sent = True

            def recv(self, n):
                if self._idx >= len(self.resp):
                    return b""
                chunk = self.resp[self._idx : self._idx + n]
                self._idx += n
                return chunk

            def close(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                pass

        mock_conn.return_value = FakeSock()
        result = camera_discovery._fetch_http_banner("1.2.3.4", 80)
        self.assertEqual(
            result,
            {"server": "Cam/1.0", "realm": "demo", "title": "Demo Cam"},
        )

    @patch("app.utils.camera_discovery.subprocess.run")
    def test_ping_latency(self, mock_run):
        class FakeProc:
            stdout = "64 bytes from 1.2.3.4: icmp_seq=1 ttl=64 time=2.3 ms"

        mock_run.return_value = FakeProc()
        latency = camera_discovery._ping_latency("1.2.3.4")
        self.assertAlmostEqual(latency, 2.3, places=1)

    @patch("app.utils.camera_discovery._mac_manufacturer")
    @patch("app.utils.camera_discovery._mac_for_ip")
    def test_add_mac_info_sets_fields(self, mock_mac_for_ip, mock_manufacturer):
        mock_mac_for_ip.return_value = "00:11:22:33:44:55"
        mock_manufacturer.return_value = "VendorX"
        cam = {"ip": "1.2.3.4", "protocol": "rtsp", "info": {}}
        camera_discovery._add_mac_info(cam)
        self.assertEqual(cam["info"].get("mac"), "00:11:22:33:44:55")
        self.assertEqual(cam["info"].get("manufacturer"), "VendorX")

    @patch("app.utils.camera_discovery._mac_for_ip", return_value=None)
    def test_add_mac_info_missing_mac(self, mock_mac_for_ip):
        cam = {"ip": "1.2.3.4", "protocol": "rtsp", "info": {}}
        camera_discovery._add_mac_info(cam)
        self.assertEqual(cam["info"], {})

    @patch("app.utils.camera_discovery._mac_for_ip")
    def test_add_mac_info_local_protocol(self, mock_mac_for_ip):
        cam = {"ip": "1.2.3.4", "protocol": "local", "info": {}}
        camera_discovery._add_mac_info(cam)
        mock_mac_for_ip.assert_not_called()
        self.assertEqual(cam["info"], {})

    @patch("app.utils.camera_discovery._ping_latency", return_value=5.0)
    @patch("app.utils.camera_discovery._detect_open_ports", return_value=[])
    @patch("app.utils.camera_discovery._probe_onvif", return_value=[])
    @patch("app.utils.camera_discovery._probe_mdns", return_value=[])
    @patch("app.utils.camera_discovery._probe_ssdp", return_value=[])
    @patch("app.utils.camera_discovery._scan_rtsp_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_rtmp_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_sip_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_webrtc_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_snmp_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_http_endpoints", return_value=[])
    @patch("app.utils.camera_discovery._scan_hls_streams", return_value=[])
    @patch("app.utils.camera_discovery._local_subnets", return_value=[])
    @patch("app.utils.camera_discovery._local_video_devices", return_value=[])
    def test_latency_in_discover(
        self,
        mock_local_video_devices,
        mock_subnets,
        *_mocks,
    ):
        cams = camera_discovery.discover_cameras()
        info = cams[0]["info"]
        self.assertIn("ping_ms", info)
        self.assertEqual(info["ping_ms"], 5.0)

    @patch("app.utils.camera_discovery._fetch_http_banner")
    @patch("app.utils.camera_discovery._detect_open_ports")
    @patch("app.utils.camera_discovery._probe_onvif", return_value=[])
    @patch("app.utils.camera_discovery._probe_mdns", return_value=[])
    @patch("app.utils.camera_discovery._probe_ssdp", return_value=[])
    @patch("app.utils.camera_discovery._scan_rtsp_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_rtmp_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_sip_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_webrtc_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_snmp_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_http_endpoints", return_value=[])
    @patch("app.utils.camera_discovery._scan_hls_streams", return_value=[])
    @patch("app.utils.camera_discovery._local_subnets", return_value=[])
    @patch("app.utils.camera_discovery._local_video_devices", return_value=[])
    def test_banner_in_discover(
        self,
        mock_local_video_devices,
        mock_subnets,
        mock_hls,
        mock_http,
        mock_snmp,
        mock_webrtc,
        mock_sip,
        mock_rtmp,
        mock_rtsp,
        mock_ssdp,
        mock_mdns,
        mock_onvif,
        mock_detect,
        mock_fetch,
    ):
        mock_detect.return_value = [80]
        mock_fetch.return_value = {"server": "CamOS"}
        cams = camera_discovery.discover_cameras()
        info = cams[0]["info"]
        self.assertIn("server", info)
        self.assertEqual(info["server"], "CamOS")

    @patch("app.utils.camera_discovery._local_subnets")
    @patch("app.utils.camera_discovery._probe_onvif", return_value=[])
    def test_custom_subnets(self, mock_onvif, mock_local_subnets):
        nets = [ip_network("10.1.1.0/30")]
        camera_discovery.discover_cameras(subnets=nets)
        mock_local_subnets.assert_not_called()

    @patch("app.utils.camera_discovery.socket.socket")
    @patch("app.utils.camera_discovery.time.time")
    def test_ssdp_scan_duration(self, mock_time, mock_socket):
        """_probe_ssdp should exit after ``max_duration`` seconds."""

        # Simulate time advancing by 0.05s on each call so the loop
        # breaks after a few iterations instead of spinning endlessly.
        t = [0.0]

        def fake_time():
            t[0] += 0.05
            return t[0]

        mock_time.side_effect = fake_time

        class FakeSock:
            def __init__(self):
                self.responses = [
                    (
                        b"HTTP/1.1 200 OK\r\nLOCATION: http://1.2.3.4\r\n\r\n",
                        ("1.2.3.4", 1900),
                    )
                ] * 10

            def settimeout(self, _):
                pass

            def sendto(self, data, addr):
                pass

            def recvfrom(self, n):
                if self.responses:
                    return self.responses.pop(0)
                raise socket.timeout

            def close(self):
                pass

        mock_socket.return_value = FakeSock()
        cams = camera_discovery._probe_ssdp(timeout=0.1, max_duration=0.2)
        # With 0.05s per iteration and a 0.2s limit we should process about
        # three responses.
        self.assertLessEqual(len(cams), 4)

    @patch("app.utils.camera_discovery._detect_open_ports", return_value=[554])
    @patch("app.utils.camera_discovery._probe_onvif", return_value=[])
    @patch("app.utils.camera_discovery._probe_mdns", return_value=[])
    @patch("app.utils.camera_discovery._probe_ssdp", return_value=[])
    @patch("app.utils.camera_discovery._scan_rtsp_ports")
    @patch("app.utils.camera_discovery._scan_rtmp_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_sip_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_webrtc_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_snmp_ports", return_value=[])
    @patch("app.utils.camera_discovery._scan_http_endpoints", return_value=[])
    @patch("app.utils.camera_discovery._scan_hls_streams", return_value=[])
    @patch("app.utils.camera_discovery._local_subnets", return_value=[])
    def test_device_type_and_url(
        self,
        mock_subnets,
        mock_hls,
        mock_http,
        mock_snmp,
        mock_webrtc,
        mock_sip,
        mock_rtmp,
        mock_rtsp,
        mock_ssdp,
        mock_mdns,
        mock_onvif,
        mock_ports,
    ):
        mock_rtsp.return_value = [
            {"ip": "1.2.3.4", "protocol": "rtsp", "port": 554, "info": {}}
        ]
        cams = camera_discovery.discover_cameras()
        cam = cams[0]
        self.assertEqual(cam.get("url"), "rtsp://1.2.3.4:554/")
        self.assertEqual(cam["info"].get("device_type"), "camera")

    @patch("app.utils.camera_discovery.requests.post")
    def test_autodetect_onvif_endpoints(self, mock_post):
        def _side_effect(url, data, timeout=3):
            if "GetCapabilities" in data:
                xml = "<Envelope><Body><Capabilities><Media><XAddr>http://1.2.3.4/onvif/media_service</XAddr></Media></Capabilities></Body></Envelope>"
            elif "GetProfiles" in data:
                xml = "<Envelope><Body><trt:GetProfilesResponse xmlns:trt='http://www.onvif.org/ver10/media/wsdl'><trt:Profiles token='p0'/></trt:GetProfilesResponse></Body></Envelope>"
            elif "GetStreamUri" in data:
                xml = "<Envelope><Body><tt:Uri xmlns:tt='http://www.onvif.org/ver10/schema'>rtsp://1.2.3.4/stream</tt:Uri></Body></Envelope>"
            else:
                xml = "<Envelope><Body><tt:Uri xmlns:tt='http://www.onvif.org/ver10/schema'>http://1.2.3.4/snap.jpg</tt:Uri></Body></Envelope>"
            return SimpleNamespace(ok=True, content=xml.encode())

        mock_post.side_effect = _side_effect
        res = camera_discovery.autodetect_onvif_endpoints("http://1.2.3.4")
        self.assertEqual(res["stream"], "rtsp://1.2.3.4/stream")
        self.assertEqual(res["snapshot"], "http://1.2.3.4/snap.jpg")

    @patch("app.utils.camera_discovery.requests.get")
    def test_remote_vendor_lookup_success(self, mock_get):
        camera_discovery._remote_vendor_lookup.cache_clear()
        mock_get.return_value = SimpleNamespace(
            status_code=200, json=lambda: {"company": "AcmeCam"}
        )
        vendor = camera_discovery._remote_vendor_lookup("00:11:22:33:44:55")
        self.assertEqual(vendor, "AcmeCam")

    @patch("app.utils.camera_discovery.requests.get")
    def test_remote_vendor_lookup_failure(self, mock_get):
        camera_discovery._remote_vendor_lookup.cache_clear()
        mock_get.side_effect = Exception("boom")
        vendor = camera_discovery._remote_vendor_lookup("00:11:22:33:44:55")
        self.assertIsNone(vendor)

    def test_load_local_ouis(self):
        """_load_local_ouis should parse valid lines and ignore others."""

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "manuf1"
            f1.write_text(
                "\n".join(
                    [
                        "# comment",
                        "001122 VendorA",
                        "33-44-55 VendorB",
                        "invalidline",
                        "00aa Short",
                    ]
                )
            )
            f2 = Path(tmpdir) / "manuf2"
            f2.write_text("66:77:88 VendorC\n")
            missing = Path(tmpdir) / "missing"

            with patch.object(
                camera_discovery,
                "_OUI_FILES",
                [str(f1), str(missing), str(f2)],
            ):
                vendors = camera_discovery._load_local_ouis()

            expected = {
                "001122": "VendorA",
                "334455": "VendorB",
                "667788": "VendorC",
            }

        expected = {"001122": "VendorA", "334455": "VendorB", "667788": "VendorC"}
        self.assertEqual(vendors, expected)


if __name__ == "__main__":
    unittest.main()
