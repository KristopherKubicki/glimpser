import socket
import uuid
import psutil
import logging
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from ipaddress import ip_network
from .screenshots import is_port_open


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
                xaddr = xml.find('.//{http://schemas.xmlsoap.org/ws/2005/04/discovery}XAddrs')
                if xaddr is not None:
                    uri = xaddr.text.split()[0]
                    parsed = urlparse(uri)
                    ip = parsed.hostname or ip
                    port = parsed.port or 80
                    info['xaddr'] = uri
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
                    found.append({"ip": ip, "protocol": "rtsp", "port": port, "info": {}})
    return found


def discover_cameras():
    """Discover cameras on the local network via ONVIF and RTSP scanning."""
    cameras = []
    cameras.extend(_probe_onvif())
    try:
        subnets = _local_subnets()
        cameras.extend(_scan_rtsp_ports(subnets))
    except Exception as e:
        logging.warning("RTSP scan error: %s", e)
    # remove duplicates
    unique = {}
    for cam in cameras:
        key = (cam['ip'], cam['protocol'], cam['port'])
        if key not in unique:
            unique[key] = cam
    return list(unique.values())
