import os
import sys
from threading import Thread
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest
import requests
from werkzeug.serving import make_server

# Provide a minimal transformers module so importing app does not require the
# real dependency, which keeps this test lightweight and offline-friendly.
dummy_tf = ModuleType("transformers")
dummy_tf.CLIPProcessor = object
dummy_tf.CLIPModel = object
sys.modules.setdefault("transformers", dummy_tf)

# Minimal stub for nodriver used by screenshots utilities.
sys.modules.setdefault("nodriver", ModuleType("nodriver"))

# Also stub the skimage.metrics module used for image comparisons.
dummy_skimage = ModuleType("skimage.metrics")
dummy_skimage.structural_similarity = lambda *a, **k: (1.0, None)
sys.modules.setdefault("skimage.metrics", dummy_skimage)

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
def auth_server(tmp_path):
    db_path = tmp_path / "test.db"

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
        patch("app.routes.login_attempts", {}),
        patch("app.config.SESSION_COOKIE_SECURE", False),
        patch.dict(os.environ, {"GLIMPSER_DATABASE_PATH": str(db_path)}),
    ]
    for p in patches:
        p.start()

    app = create_app(enable_watchdog=False, schedule=False)
    server = ServerThread(app)
    server.start()
    url = f"http://127.0.0.1:{server.port}"
    yield url
    server.shutdown()
    for p in patches:
        p.stop()


def test_health_endpoint(auth_server):
    base_url = auth_server
    session = requests.Session()
    resp = session.post(
        f"{base_url}/login",
        data={"username": "admin", "password": "pw"},
        allow_redirects=False,
    )
    assert resp.status_code == 302

    resp = session.get(f"{base_url}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in {"healthy", "degraded"}


def test_logout_redirect(auth_server):
    base_url = auth_server
    session = requests.Session()
    session.post(
        f"{base_url}/login",
        data={"username": "admin", "password": "pw"},
        allow_redirects=False,
    )
    resp = session.get(f"{base_url}/logout", allow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
