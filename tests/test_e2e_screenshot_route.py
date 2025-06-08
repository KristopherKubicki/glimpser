import os
import socket
import sys
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests
from werkzeug.serving import make_server


def _has_network() -> bool:
    """Check if outbound network access is available."""
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=1).close()
        return True
    except OSError:
        return False


if os.environ.get("SKIP_E2E") == "1" or not _has_network():
    pytest.skip("E2E tests disabled due to no network", allow_module_level=True)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app


class ServerThread(Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.server = make_server("127.0.0.1", 0, app)
        self.port = self.server.server_port

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


@pytest.fixture()
def screenshot_server(tmp_path):
    shots = tmp_path / "shots"
    shots.mkdir()

    def fake_update(name, template, motion=False):
        path = shots / name / "capture.png"
        os.makedirs(path.parent, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(b"x")

    class DummyQuery:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return SimpleNamespace(id=1, username="admin", password_hash="hash")

    class DummySession:
        def query(self, model):
            return DummyQuery()

        def close(self):
            pass

    patches = [
        patch("app.routes.check_password_hash", return_value=True),
        patch("app.routes.SessionLocal", return_value=DummySession()),
        patch(
            "app.routes.template_manager.get_templates",
            return_value={"cam1": {"name": "cam1"}},
        ),
        patch("app.routes.scheduling.update_camera", side_effect=fake_update),
        patch("app.config.SCREENSHOT_DIRECTORY", str(shots)),
        patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", str(shots)),
        patch("app.routes.login_attempts", {}),
        patch("app.config.SESSION_COOKIE_SECURE", False),
    ]
    for p in patches:
        p.start()

    app = create_app(enable_watchdog=False, schedule=False, log_cache=False)
    server = ServerThread(app)
    server.start()
    url = f"http://127.0.0.1:{server.port}"
    yield url, shots
    server.shutdown()
    for p in patches:
        p.stop()


def test_take_screenshot_route(screenshot_server):
    base_url, shots = screenshot_server
    session = requests.Session()
    resp = session.post(
        f"{base_url}/login",
        data={"username": "admin", "password": "pw"},
        allow_redirects=False,
    )
    assert resp.status_code == 302

    resp = session.get(f"{base_url}/take_screenshot/cam1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    assert os.path.exists(os.path.join(shots, "cam1", "capture.png"))
