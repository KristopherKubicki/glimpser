"""Listen outbound to existing Knox motion feeds; never change camera settings."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote, urlsplit

import requests
from requests.auth import HTTPDigestAuth

from app.utils.google_events import EventStore
from app.utils.knox_events import CAMERAS, database, frames, motion_state, record_motion
from app.utils.template_manager import get_templates

LOG = logging.getLogger(__name__)


def listen(camera):
    """Reconnect independently with bounded buffers and sanitized health."""
    store = EventStore(database())
    stats = {"started_at": time.time(), "received": 0, "accepted": 0}
    while True:
        try:
            source = urlsplit(get_templates()[camera]["url"])
            if (
                source.hostname != CAMERAS[camera]
                or not source.username
                or not source.password
            ):
                raise ValueError("Camera identity or authentication unavailable")
            auth = HTTPDigestAuth(unquote(source.username), unquote(source.password))
            # Direct LAN stream is a current observation; the firmware's DST offset
            # is inconsistent, so its clock is not used as an image capture time.
            with requests.get(
                f"http://{CAMERAS[camera]}/ISAPI/Event/notification/alertStream",
                auth=auth,
                stream=True,
                timeout=(5, 45),
                allow_redirects=False,
            ) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError("Unexpected stream response")
                store.health(camera, "connected", counters=stats)
                active = False
                checked = 0
                for xml in frames(response.iter_content(chunk_size=1)):
                    now = time.time()
                    stats["received"] += 1
                    stats["last_message_at"] = now
                    state = motion_state(xml)
                    if state == "inactive":
                        active = False
                    elif state == "active" and not active:
                        active = True
                        if record_motion(store, camera, xml, now):
                            stats["accepted"] += 1
                            stats["last_accepted_at"] = now
                    if now - checked >= 10:
                        store.health(camera, "connected", counters=stats)
                        checked = now
        except Exception as exc:
            LOG.warning("%s stream unavailable (%s)", camera, type(exc).__name__)
            store.health(camera, "unavailable", counters=stats)
        time.sleep(5)


def main():
    """One read-only connection per explicitly configured Knox camera."""
    logging.basicConfig(level=logging.INFO)
    if not CAMERAS:
        LOG.info("No native event cameras configured; subscriber disabled")
        return
    with ThreadPoolExecutor(max_workers=len(CAMERAS)) as pool:
        list(pool.map(listen, CAMERAS))


if __name__ == "__main__":
    main()
