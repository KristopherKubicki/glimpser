# Camera Discovery

Glimpser includes a simple discovery feature to help find network cameras on your local LAN. The `/discover` page in the web interface runs the logic in `app/utils/camera_discovery.py` and lists any cameras that respond.

## How the `/discover` route works

The route is defined in `app/routes.py`:

```python
@app.route('/discover', methods=['GET'])
@login_required
def discover_cameras_route():
    cameras = camera_discovery.discover_cameras()
    return render_template('discover.html', cameras=cameras)
```

When you visit `/discover`, Glimpser calls `discover_cameras()` to scan the network and then renders `discover.html` with the results.

## Camera scanning logic

The discovery code combines multiple approaches:

1. **ONVIF probe** – `_probe_onvif()` broadcasts a WS-Discovery probe and parses any replies to extract camera IP addresses and ONVIF service URLs.
2. **RTSP port scan** – `_scan_rtsp_ports()` walks through the host's local subnets and checks common RTSP ports (`554` and `8554`) using `is_port_open`.
3. **Local devices** – `_local_video_devices()` lists available `/dev/video*` entries for webcams or other direct-attached cameras.

Both sets of results are merged and returned. The key parts of the implementation are shown below:

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
                    found.append({"ip": ip, "protocol": "rtsp", "port": port, "info": {}})


def _local_video_devices(base_path="/dev"):
    for path in glob.glob(os.path.join(base_path, "video*")):
        found.append({"ip": path, "protocol": "local", "port": 0, "info": {}})
```

After scanning, `discover_cameras()` removes duplicates and returns the final list of cameras.

You can then add a discovered camera to your configuration directly from the `/discover` page.
The "Add" button on this page now includes a tooltip (title attribute) for improved accessibility.
