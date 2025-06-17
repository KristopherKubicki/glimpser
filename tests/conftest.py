import os
import sys
from types import SimpleNamespace
from datetime import datetime, timedelta

import pytest
from flask import Flask

# Skip end-to-end tests unless explicitly enabled
os.environ.setdefault("SKIP_E2E", "1")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


@pytest.fixture
def flask_app():
    template_dir = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), "../app/templates"
    )
    app = Flask(__name__, template_folder=template_dir)
    app.config["SECRET_KEY"] = "my_secret_key"
    init_routes(app)
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def dummy_user():
    return SimpleNamespace(id=1, username="testuser", password_hash="hash")


class DummyQuery:
    def __init__(self, user):
        self.user = user

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return self.user

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return []


class DummySession:
    def __init__(self, user):
        self.user = user

    def query(self, model):
        return DummyQuery(self.user)

    def close(self):
        pass


@pytest.fixture
def patch_session_local(monkeypatch, dummy_user):
    session = DummySession(dummy_user)
    monkeypatch.setattr("app.routes.SessionLocal", lambda: session)
    return session


@pytest.fixture
def reset_login_attempts(monkeypatch):
    monkeypatch.setattr("app.routes.login_attempts", {}, raising=False)


@pytest.fixture
def user_session(monkeypatch):
    sess = {
        "user_id": 1,
        "expiry": (datetime.now() + timedelta(minutes=30)).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }
    monkeypatch.setattr("app.routes.session", sess, raising=False)
    return sess
