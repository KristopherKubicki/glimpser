import glob
import logging
import os
import re
import shutil
import socket
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from ipaddress import ip_address, ip_network
from urllib.parse import urlparse

import psutil

from app.utils.api_utils import request_with_retry

from .oui_map import OUI_MAP as BUILTIN_OUI_MAP
from .chrome_utils import is_port_open

# Minimal OUI mapping for MAC manufacturer lookup.  The bulk of prefixes lives
# in ``app.utils.oui_map`` which avoids pulling in external dependencies.
OUI_MAP = BUILTIN_OUI_MAP

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


# Merge local OUI data without clobbering built‑in mappings. Some
# distributions ship different vendor names for the same prefix which can
# break unit tests expecting the bundled values.

# Defer loading of large OUI databases until needed to keep imports fast
_LOCAL_OUIS_LOADED = False


def _ensure_local_ouis_loaded() -> None:
    """Merge vendor prefixes from :data:`_OUI_FILES` into :data:`OUI_MAP`."""

    global _LOCAL_OUIS_LOADED
    if _LOCAL_OUIS_LOADED:
        return
    for _prefix, _vendor in _load_local_ouis().items():
        OUI_MAP.setdefault(_prefix, _vendor)
    _LOCAL_OUIS_LOADED = True


# Ports checked for additional metadata after discovery. The list focuses on
# common services exposed by cameras and network appliances. New ports can be
# added here without affecting the scanning steps.
COMMON_PORTS = [
    80,
    443,
    554,
    8554,
    1935,
    5060,
    5061,
    3478,
    5349,
    161,
]

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
        resp = request_with_retry("GET", MAC_VENDOR_API.format(mac), timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            vendor = data.get("company")
            if not vendor:
                vendor = data.get("vendorDetails", {}).get("companyName")
            return vendor
    except Exception:
        pass
    return None


def _onvif_get_device_info(xaddr: str, timeout: int = 2) -> dict[str, str]:
    """Return device information from an ONVIF service.

    The request is intentionally minimal and does not require authentication in
    most cases.  Any errors are silently ignored so discovery remains fast.
    """

    body = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<s:Envelope xmlns:s='http://www.w3.org/2003/05/soap-envelope'>"
        "<s:Body>"
        "<GetDeviceInformation xmlns='http://www.onvif.org/ver10/device/wsdl'/>"
        "</s:Body>"
        "</s:Envelope>"
    )
    info: dict[str, str] = {}
    try:
        resp = request_with_retry("POST", xaddr, data=body, timeout=timeout)
        if resp.ok:
            xml = ET.fromstring(resp.content)
            ns = {"tt": "http://www.onvif.org/ver10/schema"}
            for tag, key in (
                ("Manufacturer", "manufacturer"),
                ("Model", "model"),
                ("FirmwareVersion", "firmware"),
            ):
                node = xml.find(f".//tt:{tag}", ns)
                if node is not None and node.text:
                    info[key] = node.text
    except Exception:
        pass
    return info


def autodetect_onvif_endpoints(url: str, timeout: int = 3) -> dict[str, str]:
    """Return stream and snapshot URLs derived from an ONVIF device service.

    Parameters
    ----------
    url : str
        Base camera URL or ONVIF device service address.
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        Dictionary with optional ``stream`` and ``snapshot`` keys.
    """

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    xaddr = url if "device_service" in parsed.path else f"{base}/onvif/device_service"

    # Step 1: locate the media service address via GetCapabilities
    cap_body = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<s:Envelope xmlns:s='http://www.w3.org/2003/05/soap-envelope'>"
        "<s:Body>"
        "<GetCapabilities xmlns='http://www.onvif.org/ver10/device/wsdl'>"
        "<Category>All</Category>"
        "</GetCapabilities>"
        "</s:Body>"
        "</s:Envelope>"
    )
    media_addr = None
    try:
        resp = request_with_retry("POST", xaddr, data=cap_body, timeout=timeout)
        if resp.ok:
            xml = ET.fromstring(resp.content)
            ns = {"tt": "http://www.onvif.org/ver10/schema"}
            node = xml.find(".//tt:Capabilities/tt:Media/tt:XAddr", ns)
            if node is not None and node.text:
                media_addr = node.text
    except Exception:
        media_addr = None
    if not media_addr:
        media_addr = f"{base}/onvif/media_service"

    # Step 2: fetch the first profile token
    prof_body = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<s:Envelope xmlns:s='http://www.w3.org/2003/05/soap-envelope'>"
        "<s:Body>"
        "<GetProfiles xmlns='http://www.onvif.org/ver10/media/wsdl'/>"
        "</s:Body>"
        "</s:Envelope>"
    )
    token = None
    try:
        resp = request_with_retry("POST", media_addr, data=prof_body, timeout=timeout)
        if resp.ok:
            xml = ET.fromstring(resp.content)
            ns = {"trt": "http://www.onvif.org/ver10/media/wsdl"}
            prof = xml.find(".//trt:Profiles", ns)
            if prof is not None:
                token = prof.attrib.get("token")
    except Exception:
        token = None
    if not token:
        return {}

    # Step 3: fetch stream URI and snapshot URI
    result: dict[str, str] = {}
    stream_body = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<s:Envelope xmlns:s='http://www.w3.org/2003/05/soap-envelope' xmlns:trt='http://www.onvif.org/ver10/media/wsdl' xmlns:tt='http://www.onvif.org/ver10/schema'>"
        "<s:Body>"
        "<trt:GetStreamUri>"
        "<trt:StreamSetup>"
        "<tt:Stream>RTP-Unicast</tt:Stream>"
        "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport>"
        "</trt:StreamSetup>"
        f"<trt:ProfileToken>{token}</trt:ProfileToken>"
        "</trt:GetStreamUri>"
        "</s:Body>"
        "</s:Envelope>"
    )
    try:
        resp = request_with_retry("POST", media_addr, data=stream_body, timeout=timeout)
        if resp.ok:
            xml = ET.fromstring(resp.content)
            ns = {"tt": "http://www.onvif.org/ver10/schema"}
            uri = xml.find(".//tt:Uri", ns)
            if uri is not None and uri.text:
                result["stream"] = uri.text
    except Exception:
        pass

    snap_body = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<s:Envelope xmlns:s='http://www.w3.org/2003/05/soap-envelope' xmlns:trt='http://www.onvif.org/ver10/media/wsdl' xmlns:tt='http://www.onvif.org/ver10/schema'>"
        "<s:Body>"
        "<trt:GetSnapshotUri>"
        f"<trt:ProfileToken>{token}</trt:ProfileToken>"
        "</trt:GetSnapshotUri>"
        "</s:Body>"
        "</s:Envelope>"
    )
    try:
        resp = request_with_retry("POST", media_addr, data=snap_body, timeout=timeout)
        if resp.ok:
            xml = ET.fromstring(resp.content)
            ns = {"tt": "http://www.onvif.org/ver10/schema"}
            uri = xml.find(".//tt:Uri", ns)
            if uri is not None and uri.text:
                result["snapshot"] = uri.text
    except Exception:
        pass

    return result


def _mac_manufacturer(mac: str | None) -> str | None:
    """Return the vendor name for ``mac`` using known mappings or remote lookup."""

    if not mac:
        return None
    _ensure_local_ouis_loaded()
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
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        lines = proc.stdout.splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 2 and parts[1] != "*":
                return parts[1]
    except Exception as e:  # pragma: no cover - system dependent
        logging.debug("traceroute error for %s: %s", ip, e)
    return None


def _ping_latency(ip: str, timeout: int = 1) -> float | None:
    """Return ping round-trip latency to ``ip`` in milliseconds."""

    cmd = None
    if shutil.which("ping"):
        if os.name == "nt":
            cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(timeout), ip]
    if not cmd:
        return None
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 1, check=False
        )
        out = proc.stdout
        match = re.search(r"time[=<]([0-9.]+)", out)
        if not match:
            match = re.search(r"Average = ([0-9]+)ms", out)
        if match:
            return float(match.group(1))
    except Exception as e:  # pragma: no cover - system dependent
        logging.debug("ping error for %s: %s", ip, e)
    return None


def _detect_open_ports(ip: str, ports: list[int]) -> list[int]:
    """Return ports from ``ports`` that are reachable on ``ip``."""

    open_ports = []
    for port in ports:
        if is_port_open(ip, port, timeout=1):
            open_ports.append(port)
    return open_ports


def _local_subnets(max_prefixlen: int = 24):
    """Return local IPv4 subnets limited to ``max_prefixlen``.

    Some interfaces report very large networks (e.g. ``10.0.0.0/8``) which makes
    discovery scans effectively unbounded. To keep discovery responsive we cap
    the size of each subnet to at most ``max_prefixlen``. Duplicate networks are
    removed so multi-homed interfaces only scan each subnet once. Interfaces that
    are down or use loopback/link-local addresses are ignored so discovery focuses
    on routable LAN segments.
    """

    subnets: set[ip_network] = set()
    stats = psutil.net_if_stats()
    for iface, addrs in psutil.net_if_addrs().items():
        if stats.get(iface) and not stats[iface].isup:
            continue
        for addr in addrs:
            if addr.family != socket.AF_INET:
                continue
            ip = addr.address
            netmask = addr.netmask
            if not ip or not netmask:
                continue
            try:
                net = ip_network(f"{ip}/{netmask}", strict=False)
                if net.network_address.is_loopback or net.network_address.is_link_local:
                    continue
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
            except TimeoutError:
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
            # Attempt to collect detailed information using the ONVIF device
            # service. Many cameras expose this endpoint without authentication.
            # Any errors are ignored so discovery still finishes quickly.
            if info.get("xaddr"):
                try:
                    details = _onvif_get_device_info(info["xaddr"], timeout=timeout)
                    info.update(details)
                except Exception:
                    pass
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


def _probe_ssdp(timeout: int = 2, max_duration: int = 5) -> list[dict]:
    """Probe for devices announcing themselves via SSDP/UPnP.

    The loop ends after ``max_duration`` seconds regardless of how many
    responses arrive. This prevents very large networks from delaying the
    entire discovery run indefinitely.
    """

    cameras = []
    request = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST:239.255.255.250:1900\r\n"
        'MAN:"ssdp:discover"\r\n'
        "MX:1\r\n"
        "ST:ssdp:all\r\n\r\n"
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    start = time.time()
    sock.settimeout(timeout)
    try:
        sock.sendto(request.encode(), ("239.255.255.250", 1900))
        while True:
            # Break once the overall limit has expired even if the socket keeps
            # receiving new announcements. Without this check discovery could
            # stall on busy networks.
            if time.time() - start >= max_duration:
                break
            try:
                resp, addr = sock.recvfrom(1024)
            except TimeoutError:
                continue
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


def _fetch_http_banner(ip: str, port: int, timeout: int = 2) -> dict[str, str]:
    """Return HTTP metadata such as Server header or page title."""

    request = f"GET / HTTP/1.1\r\nHost: {ip}\r\nConnection: close\r\n\r\n"
    info: dict[str, str] = {}
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
                    break
        header, _, body = response.partition(b"\r\n\r\n")
        for line in header.decode(errors="ignore").split("\r\n"):
            if line.lower().startswith("server:"):
                info["server"] = line.split(":", 1)[1].strip()
            if line.lower().startswith("www-authenticate:") and 'realm="' in line:
                start = line.lower().find('realm="') + 7
                end = line.find('"', start)
                if end != -1:
                    info["realm"] = line[start:end]
        body_text = body.decode(errors="ignore")
        start_idx = body_text.lower().find("<title>")
        end_idx = body_text.lower().find("</title>", start_idx)
        if start_idx != -1 and end_idx != -1:
            title = body_text[start_idx + 7 : end_idx].strip()
            if title:
                info["title"] = title
    except Exception as e:  # pragma: no cover - network
        logging.debug("HTTP banner error for %s:%s: %s", ip, port, e)
    return info


def _default_url(cam: dict) -> str | None:
    """Return a sensible URL for ``cam`` based on its protocol."""

    ip = cam.get("ip")
    port = cam.get("port")
    proto = cam.get("protocol")
    info = cam.get("info", {})
    if proto == "rtsp":
        return f"rtsp://{ip}:{port}/"
    if proto == "rtmp":
        return f"rtmp://{ip}:{port}/live"
    if proto in {"http", "hls"}:
        path = info.get("path", "/")
        return f"http://{ip}:{port}{path}"
    if proto == "local":
        return ip
    return None


def _classify_device(cam: dict) -> str | None:
    """Return a simple device type label based on metadata."""

    info = cam.get("info", {})
    text = " ".join(str(v).lower() for v in info.values() if isinstance(v, str))
    ports = info.get("open_ports", [])
    if "nvr" in text or "dvr" in text:
        return "nvr"
    if "router" in text or "switch" in text:
        return "router"
    if "camera" in text or "onvif" in text or 554 in ports:
        return "camera"
    return None


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


def _fetch_snmp_sysdescr(ip, timeout=2) -> str | None:
    """Attempt to retrieve the SNMP sysDescr value."""
    request = bytes.fromhex(
        "30 2a 02 01 00 04 06 70 75 62 6c 69 63 A0 1d "
        "02 04 00 00 00 01 02 01 00 02 01 00 30 0f 30 0d "
        "06 08 2b 06 01 02 01 01 01 00 05 00"
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(request, (ip, 161))
        resp, _ = sock.recvfrom(4096)
        oid = b"\x06\x08\x2b\x06\x01\x02\x01\x01\x01\x00"
        idx = resp.find(oid)
        if idx != -1:
            start = idx + len(oid)
            if start + 2 <= len(resp) and resp[start] == 0x04:
                length = resp[start + 1]
                end = start + 2 + length
                return resp[start + 2 : end].decode(errors="ignore")
    except Exception:
        pass
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
                descr = _fetch_snmp_sysdescr(ip)
                if descr:
                    info["firmware"] = descr
                found.append({"ip": ip, "protocol": "snmp", "port": 161, "info": info})
    return found


def _local_video_devices(base_path="/dev"):
    """List available local video devices like /dev/video0."""
    devices = []
    for path in sorted(glob.glob(os.path.join(base_path, "video*"))):
        devices.append({"ip": path, "protocol": "local", "port": 0, "info": {}})
    return devices


def _filter_by_subnets(
    cameras: list[dict], subnets: list[ip_network] | None
) -> list[dict]:
    """Return only entries whose IP falls within ``subnets``."""

    if not subnets:
        return cameras

    filtered = []
    for cam in cameras:
        try:
            addr = ip_address(cam.get("ip"))
        except Exception:
            continue
        if any(addr in net for net in subnets):
            filtered.append(cam)
    return filtered


def discover_cameras(progress_callback=None, subnets=None):
    """Discover cameras on the local network or provided ``subnets``.

    Parameters
    ----------
    progress_callback : callable, optional
        Called with ``(stage, count, new_cameras, progress, eta)`` each time a
        discovery step completes. ``progress`` is the overall completion
        percentage and ``eta`` provides the estimated seconds remaining. The
        ``new_cameras`` argument lists entries found during that stage.
    """
    cameras: list[dict] = []

    user_subnets = subnets
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

    total_steps = len(tasks) + 1  # additional step for tracing/open port checks
    start_time = time.time()
    completed = 0

    def _report(stage, count, new):
        nonlocal completed
        completed += 1
        progress = completed / total_steps * 100
        elapsed = time.time() - start_time
        avg = elapsed / completed
        eta = max(0.0, avg * total_steps - elapsed)
        if progress_callback:
            progress_callback(stage, count, new, progress, eta)

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_to_stage = {
            executor.submit(func): stage for stage, func in tasks.items()
        }
        for fut in as_completed(future_to_stage):
            stage = future_to_stage[fut]
            stage_cameras = []
            try:
                stage_cameras = fut.result()
                if user_subnets:
                    stage_cameras = _filter_by_subnets(stage_cameras, user_subnets)
                for cam in stage_cameras:
                    _add_mac_info(cam)
                cameras.extend(stage_cameras)
            except Exception as e:  # pragma: no cover - network
                logging.warning("%s discovery error: %s", stage, e)
            finally:
                _report(stage, len(cameras), stage_cameras)

    # Always include internal views so the system can monitor itself
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

    cameras.append(
        {
            "ip": "127.0.0.1",
            "protocol": "http",
            "port": PORT,
            "info": {"name": "Internal Caption"},
            "url": f"http://127.0.0.1:{PORT}/internal_caption.mjpg",
        }
    )

    cameras.append(
        {
            "ip": "127.0.0.1",
            "protocol": "rtsp",
            "port": PORT,
            "info": {"name": "Test Frame"},
            "url": f"rtsp://127.0.0.1:{PORT}/test.rtsp",
        }
    )

    cameras.append(
        {
            "ip": "127.0.0.1",
            "protocol": "http",
            "port": PORT,
            "info": {"name": "Test Frame"},
            "url": f"http://127.0.0.1:{PORT}/test.mjpg",
        }
    )

    cameras.append(
        {
            "ip": "127.0.0.1",
            "protocol": "http",
            "port": PORT,
            "info": {"name": "Test Pattern"},
            "url": f"http://127.0.0.1:{PORT}/test_pattern.mjpg",
        }
    )

    cameras.append(
        {
            "ip": "127.0.0.1",
            "protocol": "http",
            "port": PORT,
            "info": {"name": "All Cameras"},
            "url": f"http://127.0.0.1:{PORT}/stream.mjpg?group=all",
        }
    )

    cameras.append(
        {
            "ip": "127.0.0.1",
            "protocol": "http",
            "port": PORT,
            "info": {"name": "All Motion"},
            "url": f"http://127.0.0.1:{PORT}/motion.mjpg?group=all",
        }
    )

    cameras.append(
        {
            "ip": "127.0.0.1",
            "protocol": "http",
            "port": PORT,
            "info": {"name": "All Captions"},
            "url": f"http://127.0.0.1:{PORT}/caption.mjpg?group=all",
        }
    )

    # remove duplicates but keep distinct URLs
    unique = {}
    for cam in cameras:
        key = (cam["ip"], cam["protocol"], cam["port"], cam.get("url"))
        if key not in unique:
            unique[key] = cam

    result = list(unique.values())
    for cam in result:
        _add_mac_info(cam)
        hop = _trace_upstream(cam["ip"])
        if hop:
            cam.setdefault("info", {})["upstream"] = hop
        if cam.get("protocol") != "local":
            latency = _ping_latency(cam["ip"])
            if latency is not None:
                cam.setdefault("info", {})["ping_ms"] = latency
            ports = _detect_open_ports(cam["ip"], COMMON_PORTS)
            if ports:
                info = cam.setdefault("info", {})
                info["open_ports"] = ports
                for p in ports:
                    if p in (80, 8080, 443):
                        banner = _fetch_http_banner(cam["ip"], p)
                        for k, v in banner.items():
                            info.setdefault(k, v)
        if "url" not in cam:
            url = _default_url(cam)
            if url:
                cam["url"] = url
        dtype = _classify_device(cam)
        if dtype:
            cam.setdefault("info", {})["device_type"] = dtype

    _report("trace", len(result), [])

    return result
