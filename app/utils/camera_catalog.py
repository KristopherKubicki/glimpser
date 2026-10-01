"""Public camera map inventory independent of dashboard membership."""

from urllib.parse import urlsplit

from app.utils.visual_dashboard import build_visual_dashboard

NON_CAMERA = {
    "SigAlert",
    "Wind",
    "Lightning2",
    "Fires",
    "GPSJam",
    "ORDApproachADSBMap",
    "MDWApproachADSBMap",
}
CAMERA_HOSTS = (
    "instacam.com",
    "earthcam.com",
    "wetmet.net",
    "ytimg.com",
    "skylinewebcams.com",
    "travelmidwest.com",
    "lakecountypassage.com",
    "511wi.gov",
    "mackinacbridge.org",
)


def build_camera_catalog(templates: dict) -> dict:
    """Expose camera presentation fields, excluding private and non-camera points."""
    visible = {}
    for name, details in templates.items():
        groups = set(str(details.get("groups") or "").lower().split(","))
        if (
            name in NON_CAMERA
            or details.get("private_camera")
            or details.get("camera_location_private")
            or "private" in groups
        ):
            continue
        visible[name] = details
    cameras = build_visual_dashboard(visible, "")["cameras"]
    mapped, unmapped = [], []
    for camera in cameras:
        details = visible[camera["name"]]
        if camera["location"]:
            mapped.append(camera)
            continue
        url = str(details.get("url") or "")
        host = urlsplit(url).hostname or ""
        if (
            any(host == h or host.endswith("." + h) for h in CAMERA_HOSTS)
            or "/metdata/" in url
            or camera["name"] in {"NIUEast", "SaltCreekWoodDale", "Elmhurst"}
        ):
            unmapped.append(camera)
    sites = {
        (round(c["location"]["lat"], 4), round(c["location"]["lon"], 4)) for c in mapped
    }
    return {
        "cameras": mapped,
        "unmapped_cameras": unmapped,
        "coverage": {
            "mapped_views": len(mapped),
            "mapped_sites": len(sites),
            "unmapped_views": len(unmapped),
        },
    }
