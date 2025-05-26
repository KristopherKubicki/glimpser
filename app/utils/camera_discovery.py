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
from .screenshots import is_port_open

# Pre-built SNMPv1 GET request for sysName.0 using the "public" community.
# This avoids requiring external dependencies and is sufficient for checking
# whether a device responds to basic SNMP queries.
SNMP_SYSNAME_REQUEST = bytes(
    [
        0x30,
        0x26,
        0x02,
        0x01,
        0x00,
        0x04,
        0x06,
        0x70,
        0x75,
        0x62,
        0x6C,
        0x69,
        0x63,
        0xA0,
        0x19,
        0x02,
        0x01,
        0x01,
        0x02,
        0x01,
        0x00,
        0x02,
        0x01,
        0x00,
        0x30,
        0x0E,
        0x30,
        0x0C,
        0x06,
        0x08,
        0x2B,
        0x06,
        0x01,
        0x02,
        0x01,
        0x01,
        0x05,
        0x00,
        0x05,
        0x00,
    ]
)

try:  # optional Zeroconf support
    from zeroconf import ServiceBrowser, Zeroconf
except Exception:  # pragma: no cover - optional dependency may be missing
    Zeroconf = None


def _local_subnets():
    subnets = []
    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                ip = addr.address
                netmask = addr.netmask
                if ip and netmask:
                    try:
                        subnets.append(ip_network(f"{ip}/{netmask}", strict=False))
                    except Exception:
                        pass
    return subnets


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
                    found.append(
                        {"ip": ip, "protocol": "rtsp", "port": port, "info": {}}
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


def _snmp_get_sysname(ip, community="public", timeout=1):
    """Return the sysName via SNMP or None if the host does not respond."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.sendto(SNMP_SYSNAME_REQUEST, (ip, 161))
            data, _ = sock.recvfrom(512)
        except (socket.timeout, OSError):
            return None

    # The response includes the requested OID followed by an OctetString.
    oid = b"\x06\x08\x2b\x06\x01\x02\x01\x01\x05\x00"
    idx = data.find(oid)
    if idx == -1:
        return None
    idx += len(oid)
    if idx + 2 > len(data) or data[idx] != 0x04:
        return None
    length = data[idx + 1]
    value = data[idx + 2 : idx + 2 + length]
    try:
        return value.decode(errors="ignore")
    except Exception:
        return None


def _probe_snmp(subnets):
    """Probe hosts via SNMP to see if they respond to sysName queries."""
    found = []
    checked = set()
    for net in subnets:
        for host in net.hosts():
            ip = str(host)
            if ip in checked:
                continue
            checked.add(ip)
            name = _snmp_get_sysname(ip)
            if name:
                found.append(
                    {"ip": ip, "protocol": "snmp", "port": 161, "info": {"name": name}}
                )
    return found


def _local_video_devices(base_path="/dev"):
    """List available local video devices like /dev/video0."""
    devices = []
    for path in sorted(glob.glob(os.path.join(base_path, "video*"))):
        devices.append({"ip": path, "protocol": "local", "port": 0, "info": {}})
    return devices


def discover_cameras():
    """Discover cameras on the local network."""
    cameras = []
    cameras.extend(_probe_onvif())
    try:
        cameras.extend(_probe_mdns())
    except Exception as e:
        logging.debug("mDNS discovery error: %s", e)
    try:
        subnets = _local_subnets()
        cameras.extend(_scan_rtsp_ports(subnets))
        cameras.extend(_scan_rtmp_ports(subnets))
        cameras.extend(_probe_snmp(subnets))
    except Exception as e:
        logging.warning("RTSP scan error: %s", e)
    try:
        cameras.extend(_local_video_devices())
    except Exception as e:
        logging.debug("local video scan error: %s", e)

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
    return list(unique.values())
