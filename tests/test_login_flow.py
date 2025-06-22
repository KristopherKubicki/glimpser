import importlib
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import app


@pytest.fixture()
def test_client(tmp_path):
    db_path = tmp_path / "test.db"
    env_patch = patch.dict(os.environ, {"GLIMPSER_DATABASE_PATH": str(db_path)})
    env_patch.start()

    secure_patch = patch("app.config.SESSION_COOKIE_SECURE", False)
    secure_patch.start()

    import app.config as config
    import app.routes as routes
    import app.utils.db as db
    import generate_credentials

    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(routes)
    importlib.reload(app)

    args = SimpleNamespace(
        db_path=str(db_path),
        username="testuser",
        password="secret",  # pragma: allowlist secret
        update_password=False,
        secret_key="secretkey",  # pragma: allowlist secret
        update_key=False,
    )
    generate_credentials.generate_credentials(args)

    application = app.create_app(enable_watchdog=False, schedule=False, log_cache=False)
    client = application.test_client()
    ctx = application.app_context()
    ctx.push()

    yield client

    ctx.pop()
    env_patch.stop()
    secure_patch.stop()

    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(routes)
    importlib.reload(app)


def test_login_logout_flow(test_client):
    response = test_client.post(
        "/login",
        data={"username": "testuser", "password": "secret"},  # pragma: allowlist secret
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")

    response = test_client.get("/logout")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
