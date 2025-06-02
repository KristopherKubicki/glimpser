# Camera Discovery

Glimpser includes a simple discovery feature to help find network cameras on your local LAN. The `/discover` page now loads immediately and only scans when you click the **Discover** button. A progress bar displays the number of completed stages so you know the scan is making progress. The page also shows which discovery stage is currently executing. The logic in `app/utils/camera_discovery.py` runs in parallel threads so results return faster. To keep the scan quick, each interface is limited to a `/24` subnet even if the reported mask is larger.
The subnet list is now deduplicated so machines with multiple addresses per interface are scanned only once. Unreachable ports fail fast so discovery always completes even when some networks are inaccessible.
After all scanning steps finish, Glimpser performs a two-hop traceroute to each
discovered camera. The previous hop is stored in the ``upstream`` field so you
can see which router or switch connects the device.

## How the `/discover` route works

The route is defined in `app/routes.py`:

```python
@app.route('/discover', methods=['GET'])
@login_required
def discover_cameras_route():
    return render_template('discover.html', cameras=[])

@app.route('/discover/scan_stream')
@login_required
def discover_cameras_scan_stream():
    def generate():
        ...  # yields progress events
    return Response(stream_with_context(generate()), mimetype='text/event-stream')
```

When you visit `/discover`, the page loads instantly with an empty list. Clicking the **Discover** button opens an EventSource to `/discover/scan_stream`. The first message now includes the list of subnets that will be scanned and the full plan of discovery stages. The progress bar is initialized with the total number of stages. Each subsequent message indicates which stage has finished, how many cameras have been found so far, and includes any new cameras discovered during that stage. These cameras appear in the table immediately. A final event with ``{"done": true}`` simply signals completion.

An optional CIDR can be supplied via the new input field to restrict discovery to a specific Class C network. The value is sent as the ``cidr`` query parameter and parsed by ``discover_cameras()``.

During the scan you will see messages like `Scanning onvif (3 found)...`. The stage name shows which discovery method just finished, while the number in parentheses reflects how many cameras have been detected so far.

## Camera scanning logic

The discovery code combines multiple approaches:

1. **ONVIF probe** – `_probe_onvif()` broadcasts a WS-Discovery probe and parses any replies to extract camera IP addresses and ONVIF service URLs.
2. **RTSP port scan** – `_scan_rtsp_ports()` checks common RTSP ports (`554` and `8554`). When a port is open it sends a DESCRIBE request to retrieve the stream's SDP, if available.
3. **RTMP port scan** – `_scan_rtmp_ports()` checks each subnet for the default RTMP port (`1935`).
4. **SIP port scan** – `_scan_sip_ports()` looks for SIP endpoints on ports `5060` and `5061`.
5. **WebRTC/STUN scan** – `_scan_webrtc_ports()` detects WebRTC servers by checking ports `3478` and `5349`.
6. **mDNS/Zeroconf** – `_probe_mdns()` looks for services like `_onvif._tcp` and `_rtsp._tcp` advertised on the local network.
7. **SNMP scan** – `_scan_snmp_ports()` checks port `161` for SNMP agents and reads the device name if possible.
8. **SSDP/UPnP probe** – `_probe_ssdp()` sends an M-SEARCH request to detect cameras announcing via SSDP.
9. **HTTP endpoint scan** – `_scan_http_endpoints()` checks ports `80`, `8080`, and `443` for `/snapshot.jpg` or `/video.mjpg` streams.
10. **HLS detection** – `_scan_hls_streams()` looks for playlist files like `/index.m3u8`.
11. **Local devices** – `_local_video_devices()` lists available `/dev/video*` entries for webcams or other direct-attached cameras.
12. **Traceroute hop** – `_trace_upstream()` runs a quick traceroute limited to
    two hops and records the previous hop for each camera.

All discovered entries are merged and returned. The key parts of the implementation are shown below:

```python
# app/utils/camera_discovery.py

def _probe_onvif(timeout=2):
    ...
    sock.sendto(probe.encode(), ("239.255.255.250", 3702))
    ...
    cameras.append({"ip": ip, "protocol": "onvif", "port": port, "info": info})


def _scan_rtsp_ports(subnets):
    for net in subnets:
        for host in net.hosts():
            ...
            for port in (554, 8554):
                if is_port_open(ip, port, timeout=1):
                    info = {}
                    sdp = _fetch_sdp(ip, port)
                    if sdp:
                        info["sdp"] = sdp
                    found.append({"ip": ip, "protocol": "rtsp", "port": port, "info": info})


def _scan_rtmp_ports(subnets):
    for net in subnets:
        for host in net.hosts():
            ...
            if is_port_open(ip, 1935, timeout=1):
                found.append({"ip": ip, "protocol": "rtmp", "port": 1935, "info": {}})


def _scan_sip_ports(subnets):
    for net in subnets:
        for host in net.hosts():
            ...
            for port in (5060, 5061):
                if is_port_open(ip, port, timeout=1):
                    found.append({"ip": ip, "protocol": "sip", "port": port, "info": {}})


def _scan_webrtc_ports(subnets):
    for net in subnets:
        for host in net.hosts():
            ...
            for port in (3478, 5349):
                if is_port_open(ip, port, timeout=1):
                    found.append({"ip": ip, "protocol": "webrtc", "port": port, "info": {}})


def _scan_snmp_ports(subnets):
    for net in subnets:
        for host in net.hosts():
            ...
            if is_port_open(ip, 161, timeout=1):
                name = _fetch_snmp_sysname(ip)
                info = {"name": name} if name else {}
                found.append({"ip": ip, "protocol": "snmp", "port": 161, "info": info})


def _scan_http_endpoints(subnets):
    for net in subnets:
        for host in net.hosts():
            ...
            for port in (80, 8080, 443):
                if is_port_open(ip, port, timeout=1):
                    if _check_http_endpoint(ip, port, "/snapshot.jpg", timeout=1):
                        found.append({"ip": ip, "protocol": "http", "port": port, "info": {"path": "/snapshot.jpg"}})


def _scan_hls_streams(subnets):
    for net in subnets:
        for host in net.hosts():
            ...
            for port in (80, 8080, 443):
                if is_port_open(ip, port, timeout=1):
                    if _check_http_endpoint(ip, port, "/index.m3u8", timeout=1):
                        found.append({"ip": ip, "protocol": "hls", "port": port, "info": {"path": "/index.m3u8"}})


def _local_video_devices(base_path="/dev"):
    for path in glob.glob(os.path.join(base_path, "video*")):
        found.append({"ip": path, "protocol": "local", "port": 0, "info": {}})
```

After scanning, `discover_cameras()` removes duplicates and returns the final list of cameras.

Each entry is also augmented with the device's MAC address and, when known,
the manufacturer derived from its OUI prefix.  Glimpser consults local OUI
databases such as `nmap-mac-prefixes` or `manuf` when present and falls back to
an online lookup service if necessary so most devices report a recognizable
brand.
These details appear as separate
columns in the discovery table so you can quickly identify where each camera
originates. This information is now available in the incremental results
streamed back to the page during scanning. The **Info** column summarizes key
details such as a camera's name, ONVIF address, or HTTP path instead of showing
the raw JSON dictionary.

You can then add a discovered camera to your configuration directly from the `/discover` page.
The "Add" button on this page now includes a tooltip (title attribute) for improved accessibility.

The discovery list also shows a **System Status** entry pointing at your local
`/status` page (`http://127.0.0.1:8082/status`). You can add this item like any
other camera to have Glimpser periodically capture screenshots of its own
metrics page.

## Common cameras to try

Any IP camera that supports **ONVIF**, **RTSP**, **RTMP**, **HTTP/MJPEG**, or **HLS** streams should show
up in the discovery list. The following brands are frequently used and respond
well to the existing discovery methods:

- **Amcrest** – consumer-grade cameras with reliable ONVIF support.
- **Hikvision/Dahua** – widely deployed security cameras that offer RTSP
  streams.
- **Axis** – enterprise cameras known for robust network features.
- **Foscam** – budget-friendly cameras often found in home setups.

Locally attached USB webcams (for example, Logitech devices) will appear under
`/dev/video*`.

Remote sources such as **GOES16**, **ZoomEarth**, and **Dopler** can be added
manually, but they are not discovered automatically because they are hosted
outside the local network.
