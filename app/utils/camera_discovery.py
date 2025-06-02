import socket
import uuid
import psutil
import logging
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from ipaddress import ip_network
import os
import glob
import time
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import shutil

import requests

from .screenshots import is_port_open

# Minimal OUI mapping for MAC manufacturer lookup.  This avoids pulling in
# extra dependencies while still providing useful vendor hints.  Only a few
# common prefixes are included.
OUI_MAP = {
    "000c29": "VMware",
    "525400": "QEMU",
    "080027": "VirtualBox",
    # Common router and camera vendors
    "d850e6": "ASUSTek",
    "50e549": "ASUSTek",
    "0017c8": "Netgear",
    "a0cec8": "Netgear",
    "00040e": "D-Link",
    "b0b2dc": "TP-Link",
    "28c68e": "TP-Link",
    "fcdbb3": "Ubiquiti",
    "7cf2c8": "Ubiquiti",
    "001e58": "Hikvision",
    "18a6f7": "Amcrest",
    "00265e": "Axis",
}

# Possible locations of large OUI databases to supplement :data:`OUI_MAP`.
_OUI_FILES = [
    "/usr/share/nmap/nmap-mac-prefixes",
    "/usr/share/wireshark/manuf",
]


def _load_local_ouis() -> dict[str, str]:
    """Return additional vendor prefixes from common system files."""

    vendors: dict[str, str] = {}
    for path in _OUI_FILES:
        try:
            with open(path) as fh:
                for line in fh:
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    prefix = parts[0].replace("-", "").replace(":", "").lower()
                    if len(prefix) >= 6 and prefix[:6] not in vendors:
                        vendors[prefix[:6]] = parts[1]
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return vendors


OUI_MAP.update(_load_local_ouis())

# Discovery steps executed by :func:`discover_cameras`.  The list order
# defines both the execution order and the number of progress updates.
DISCOVERY_STAGES = [
    "onvif",
    "ssdp",
    "mdns",
    "rtsp",
    "rtmp",
    "sip",
    "webrtc",
    "snmp",
    "http",
    "hls",
    "local",
    "trace",
]


def get_discovery_stages() -> list[str]:
    """Return the list of discovery stage names."""

    return DISCOVERY_STAGES.copy()


try:  # optional Zeroconf support
    from zeroconf import ServiceBrowser, Zeroconf
except Exception:  # pragma: no cover - optional dependency may be missing
    Zeroconf = None


def _mac_for_ip(ip: str) -> str | None:
    """Return the MAC address for ``ip`` from the ARP table if available."""

    try:
        with open("/proc/net/arp") as fh:
            next(fh)
            for line in fh:
                parts = line.split()
                if parts and parts[0] == ip:
                    return parts[3].lower()
    except Exception:
        pass
    return None


MAC_VENDOR_API = "https://api.maclookup.app/v2/macs/{}"


@lru_cache(maxsize=1024)
def _remote_vendor_lookup(mac: str) -> str | None:
    """Return vendor name for ``mac`` via maclookup API."""

    try:  # network access might fail; ignore errors
        resp = requests.get(MAC_VENDOR_API.format(mac), timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            vendor = data.get("company")
            if not vendor:
                vendor = data.get("vendorDetails", {}).get("companyName")
            return vendor
    except Exception:
        pass
    return None


def _mac_manufacturer(mac: str | None) -> str | None:
    """Return the vendor name for ``mac`` using known mappings or remote lookup."""

    if not mac:
        return None
    prefix = mac.replace(":", "").lower()[:6]
    vendor = OUI_MAP.get(prefix)
    if vendor:
        return vendor
    vendor = _remote_vendor_lookup(mac)
    if vendor:
        OUI_MAP[prefix] = vendor  # cache for future calls
    return vendor


def _add_mac_info(cam: dict) -> None:
    """Augment ``cam`` with MAC and vendor information if possible."""

    if cam.get("protocol") == "local":
        return
    mac = _mac_for_ip(cam.get("ip"))
    if mac:
        info = cam.setdefault("info", {})
        info["mac"] = mac
        vendor = _mac_manufacturer(mac)
        if vendor:
            info["manufacturer"] = vendor


def _trace_upstream(ip: str, timeout: int = 3) -> str | None:
    """Return the first hop when tracing ``ip``.

    The function invokes the system ``traceroute`` (or ``tracert`` on
    Windows) limited to two hops so discovery remains quick.  The IP of
    the first hop is returned, representing the router or switch just
    before the camera.  Any errors are ignored and ``None`` is returned.
    """

    cmd = None
    if shutil.which("traceroute"):
        cmd = ["traceroute", "-n", "-m", "2", ip]
    elif shutil.which("tracert"):
        cmd = ["tracert", "-d", "-h", "2", ip]
    if not cmd:
        return None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        lines = proc.stdout.splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 2 and parts[1] != "*":
                return parts[1]
    except Exception as e:  # pragma: no cover - system dependent
        logging.debug("traceroute error for %s: %s", ip, e)
    return None


def _local_subnets(max_prefixlen: int = 24):
    """Return local IPv4 subnets limited to ``max_prefixlen``.

    Some interfaces report very large networks (e.g. ``10.0.0.0/8``) which makes
    discovery scans effectively unbounded. To keep discovery responsive we cap
    the size of each subnet to at most ``max_prefixlen``. Duplicate networks are
    removed so multi-homed interfaces only scan each subnet once.
    """

    subnets: set[ip_network] = set()
    for addrs in psutil.net_if_addrs().values():
        for addr in addrs:
            if addr.family != socket.AF_INET:
                continue
            ip = addr.address
            netmask = addr.netmask
            if not ip or not netmask:
                continue
            try:
                net = ip_network(f"{ip}/{netmask}", strict=False)
                if net.prefixlen < max_prefixlen:
                    net = ip_network(f"{ip}/{max_prefixlen}", strict=False)
                subnets.add(net)
            except Exception:
                continue

    return sorted(subnets, key=lambda n: (n.network_address.packed, n.prefixlen))


def _probe_onvif(timeout=2):
    cameras = []
    message_id = uuid.uuid4()
    probe = f"""<?xml version='1.0' encoding='UTF-8'?>
        <e:Envelope xmlns:e='http://www.w3.org/2003/05/soap-envelope' xmlns:w='http://schemas.xmlsoap.org/ws/2004/08/addressing' xmlns:d='http://schemas.xmlsoap.org/ws/2005/04/discovery'>
            <e:Header>
                <w:MessageID>uuid:{message_id}</w:MessageID>
                <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
                <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
            </e:Header>
            <e:Body>
                <d:Probe>
                    <d:Types>dn:NetworkVideoTransmitter</d:Types>
                </d:Probe>
            </e:Body>
        </e:Envelope>"""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(timeout)
    try:
        sock.sendto(probe.encode(), ("239.255.255.250", 3702))
        while True:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                break
            ip = addr[0]
            info = {}
            try:
                xml = ET.fromstring(data)
                xaddr = xml.find(
                    ".//{http://schemas.xmlsoap.org/ws/2005/04/discovery}XAddrs"
                )
                if xaddr is not None:
                    uri = xaddr.text.split()[0]
                    parsed = urlparse(uri)
                    ip = parsed.hostname or ip
                    port = parsed.port or 80
                    info["xaddr"] = uri
                else:
                    port = 80
            except Exception as e:
                logging.debug("parse error: %s", e)
                port = 80
            cameras.append({"ip": ip, "protocol": "onvif", "port": port, "info": info})
    except Exception as e:
        logging.warning("ONVIF discovery error: %s", e)
    finally:
        sock.close()
    return cameras


def _probe_mdns(timeout=2):
    """Discover cameras advertised via mDNS/Zeroconf."""
    cameras = []
    if Zeroconf is None:
        return cameras

    class _Listener:
        def add_service(self, zc, service_type, name):  # pragma: no cover - network
            info = zc.get_service_info(service_type, name)
            if info and info.addresses:
                ip = socket.inet_ntoa(info.addresses[0])
                cameras.append(
                    {
                        "ip": ip,
                        "protocol": "mdns",
                        "port": info.port,
                        "info": {"name": name},
                    }
                )

    zc = Zeroconf()
    listener = _Listener()
    services = ["_onvif._tcp.local.", "_rtsp._tcp.local."]
    browsers = [ServiceBrowser(zc, s, listener) for s in services]
    time.sleep(timeout)
    for b in browsers:  # pragma: no cover - network
        b.cancel()
    zc.close()
    return cameras


def _probe_ssdp(timeout=2):
    """Probe for devices announcing themselves via SSDP/UPnP."""
    cameras = []
    request = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST:239.255.255.250:1900\r\n"
        'MAN:"ssdp:discover"\r\n'
        "MX:1\r\n"
        "ST:ssdp:all\r\n\r\n"
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(timeout)
    try:
        sock.sendto(request.encode(), ("239.255.255.250", 1900))
        while True:
            try:
                resp, addr = sock.recvfrom(1024)
            except socket.timeout:
                break
            ip = addr[0]
            port = 80
            headers = resp.decode(errors="ignore").split("\r\n")
            for line in headers:
                if line.lower().startswith("location:"):
                    try:
                        url = urlparse(line.split(":", 1)[1].strip())
                        ip = url.hostname or ip
                        port = url.port or port
                    except Exception:
                        pass
                    break
            cameras.append({"ip": ip, "protocol": "ssdp", "port": port, "info": {}})
    except Exception as e:
        logging.debug("SSDP probe error: %s", e)
    finally:
        sock.close()
    return cameras


def _fetch_sdp(ip, port, timeout=2):
    """Attempt to retrieve an SDP description from an RTSP endpoint."""
    request = (
        f"DESCRIBE rtsp://{ip}:{port}/ RTSP/1.0\r\n"
        "CSeq: 1\r\n"
        "Accept: application/sdp\r\n\r\n"
    )
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.sendall(request.encode())
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                if b"\r\n\r\n" in response:
                    # headers done; assume SDP follows
                    break
        header, _, body = response.partition(b"\r\n\r\n")
        if b"200" not in header.split(b"\r\n")[0]:
            return None
        return body.decode(errors="ignore")
    except Exception as e:  # pragma: no cover - network
        logging.debug("SDP fetch error for %s:%s: %s", ip, port, e)
        return None


def _check_http_endpoint(ip: str, port: int, path: str, timeout: int = 2) -> bool:
    """Return True if an HTTP GET returns status 200."""
    request = f"GET {path} HTTP/1.1\r\nHost: {ip}\r\nConnection: close\r\n\r\n"
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.sendall(request.encode())
            resp = sock.recv(64)
            return resp.startswith(b"HTTP/1") and b"200" in resp.split(b"\r\n")[0]
    except Exception as e:  # pragma: no cover - network
        logging.debug("HTTP check error for %s:%s%s: %s", ip, port, path, e)
        return False


def _scan_rtsp_ports(subnets):
    found = []
    checked = set()
    for net in subnets:
        for host in net.hosts():
            ip = str(host)
            if ip in checked:
                continue
            checked.add(ip)
            for port in (554, 8554):
                if is_port_open(ip, port, timeout=1):
                    info = {}
                    sdp = _fetch_sdp(ip, port)
                    if sdp:
                        info["sdp"] = sdp
                    found.append(
                        {"ip": ip, "protocol": "rtsp", "port": port, "info": info}
                    )
    return found


def _scan_rtmp_ports(subnets):
    """Scan common RTMP port 1935 across subnets."""
    found = []
    checked = set()
    for net in subnets:
        for host in net.hosts():
            ip = str(host)
            if ip in checked:
                continue
            checked.add(ip)
            if is_port_open(ip, 1935, timeout=1):
                found.append({"ip": ip, "protocol": "rtmp", "port": 1935, "info": {}})
    return found


def _scan_http_endpoints(subnets):
    """Scan HTTP ports for MJPEG/snapshot URLs."""
    paths = ["/snapshot.jpg", "/video.mjpg"]
    found = []
    checked: set[str] = set()
    for net in subnets:
        for host in net.hosts():
            ip = str(host)
            if ip in checked:
                continue
            checked.add(ip)
            for port in (80, 8080, 443):
                if not is_port_open(ip, port, timeout=1):
                    continue
                for path in paths:
                    if _check_http_endpoint(ip, port, path, timeout=1):
                        found.append(
                            {
                                "ip": ip,
                                "protocol": "http",
                                "port": port,
                                "info": {"path": path},
                            }
                        )
                        break
    return found


def _scan_hls_streams(subnets):
    """Scan HTTP ports for HLS playlists."""
    playlists = ["/index.m3u8", "/live.m3u8"]
    found = []
    checked: set[str] = set()
    for net in subnets:
        for host in net.hosts():
            ip = str(host)
            if ip in checked:
                continue
            checked.add(ip)
            for port in (80, 8080, 443):
                if not is_port_open(ip, port, timeout=1):
                    continue
                for path in playlists:
                    if _check_http_endpoint(ip, port, path, timeout=1):
                        found.append(
                            {
                                "ip": ip,
                                "protocol": "hls",
                                "port": port,
                                "info": {"path": path},
                            }
                        )
                        break
    return found


def _scan_sip_ports(subnets):
    """Scan common SIP ports across subnets."""
    found = []
    checked = set()
    for net in subnets:
        for host in net.hosts():
            ip = str(host)
            if ip in checked:
                continue
            checked.add(ip)
            for port in (5060, 5061):
                if is_port_open(ip, port, timeout=1):
                    found.append(
                        {"ip": ip, "protocol": "sip", "port": port, "info": {}}
                    )
    return found


def _scan_webrtc_ports(subnets):
    """Scan common WebRTC/STUN ports across subnets."""
    found = []
    checked = set()
    for net in subnets:
        for host in net.hosts():
            ip = str(host)
            if ip in checked:
                continue
            checked.add(ip)
            for port in (3478, 5349):
                if is_port_open(ip, port, timeout=1):
                    found.append(
                        {"ip": ip, "protocol": "webrtc", "port": port, "info": {}}
                    )
    return found


def _fetch_snmp_sysname(ip, timeout=2):
    """Attempt to retrieve the SNMP sysName value."""
    # Minimal SNMPv1 GET request for OID 1.3.6.1.2.1.1.5.0 (sysName)
    request = bytes.fromhex(
        "30 2a 02 01 00 04 06 70 75 62 6c 69 63 A0 1d "
        "02 04 00 00 00 01 02 01 00 02 01 00 30 0f 30 0d "
        "06 08 2b 06 01 02 01 01 05 00 05 00"
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(request, (ip, 161))
        resp, _ = sock.recvfrom(4096)
        oid = b"\x06\x08\x2b\x06\x01\x02\x01\x01\x05\x00"
        idx = resp.find(oid)
        if idx != -1:
            start = idx + len(oid)
            if start + 2 <= len(resp) and resp[start] == 0x04:
                length = resp[start + 1]
                end = start + 2 + length
                return resp[start + 2 : end].decode(errors="ignore")
    except Exception as e:  # pragma: no cover - network
        logging.debug("SNMP fetch error for %s: %s", ip, e)
    finally:
        sock.close()
    return None


def _scan_snmp_ports(subnets):
    """Scan SNMP port 161 across subnets."""
    found = []
    checked = set()
    for net in subnets:
        for host in net.hosts():
            ip = str(host)
            if ip in checked:
                continue
            checked.add(ip)
            if is_port_open(ip, 161, timeout=1):
                info = {}
                name = _fetch_snmp_sysname(ip)
                if name:
                    info["name"] = name
                found.append({"ip": ip, "protocol": "snmp", "port": 161, "info": info})
    return found


def _local_video_devices(base_path="/dev"):
    """List available local video devices like /dev/video0."""
    devices = []
    for path in sorted(glob.glob(os.path.join(base_path, "video*"))):
        devices.append({"ip": path, "protocol": "local", "port": 0, "info": {}})
    return devices


def discover_cameras(progress_callback=None, subnets=None):
    """Discover cameras on the local network or provided ``subnets``.

    Parameters
    ----------
    progress_callback : callable, optional
        Called with ``(stage, count, new_cameras)`` each time a discovery
        step completes. ``new_cameras`` is the list of cameras found during
        that stage.
    """
    cameras: list[dict] = []

    if subnets is None:
        try:
            subnets = _local_subnets()
        except Exception as e:  # pragma: no cover - system dependent
            logging.warning("subnet discovery error: %s", e)
            subnets = []

    tasks = {
        "onvif": _probe_onvif,
        "ssdp": _probe_ssdp,
        "mdns": _probe_mdns,
        "rtsp": lambda: _scan_rtsp_ports(subnets),
        "rtmp": lambda: _scan_rtmp_ports(subnets),
        "sip": lambda: _scan_sip_ports(subnets),
        "webrtc": lambda: _scan_webrtc_ports(subnets),
        "snmp": lambda: _scan_snmp_ports(subnets),
        "http": lambda: _scan_http_endpoints(subnets),
        "hls": lambda: _scan_hls_streams(subnets),
        "local": _local_video_devices,
    }

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_to_stage = {
            executor.submit(func): stage for stage, func in tasks.items()
        }
        for fut in as_completed(future_to_stage):
            stage = future_to_stage[fut]
            stage_cameras = []
            try:
                stage_cameras = fut.result()
                for cam in stage_cameras:
                    _add_mac_info(cam)
                cameras.extend(stage_cameras)
            except Exception as e:  # pragma: no cover - network
                logging.warning("%s discovery error: %s", stage, e)
            finally:
                if progress_callback:
                    progress_callback(stage, len(cameras), stage_cameras)

    # Always include the internal status page so the system can monitor itself
    from app.config import PORT

    cameras.append(
        {
            "ip": "127.0.0.1",
            "protocol": "http",
            "port": PORT,
            "info": {"name": "System Status"},
            "url": f"http://127.0.0.1:{PORT}/status",
        }
    )
    # remove duplicates
    unique = {}
    for cam in cameras:
        key = (cam["ip"], cam["protocol"], cam["port"])
        if key not in unique:
            unique[key] = cam

    result = list(unique.values())
    for cam in result:
        _add_mac_info(cam)
        hop = _trace_upstream(cam["ip"])
        if hop:
            cam.setdefault("info", {})["upstream"] = hop

    if progress_callback:
        progress_callback("trace", len(result), [])

    return result
