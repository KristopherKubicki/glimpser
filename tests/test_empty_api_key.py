from unittest.mock import patch

import pytest
from flask import Flask

from app import routes


@pytest.mark.parametrize("configured", [None, "", "   ", "configured-test-key"])
@pytest.mark.parametrize("submitted", [None, "", "wrong-test-key"])
def test_empty_or_wrong_api_key_never_authorizes(configured, submitted):
    app = Flask(__name__)
    app.secret_key = "isolated-test-session"
    app.add_url_rule("/login", "login", lambda: "login")
    calls = []

    @routes.login_required
    def protected():
        calls.append(True)
        return "protected"

    with (
        patch.object(routes, "API_KEY", configured),
        patch.object(routes.config, "SKIP_LOGIN_SUBNETS", []),
    ):
        with app.test_request_context(
            "/protected",
            method="POST",
            data={} if submitted is None else {"api_key": submitted},
        ):
            protected()
    assert calls == []


def test_nonempty_matching_api_key_authorizes():
    app = Flask(__name__)
    with (
        patch.object(routes, "API_KEY", "matching-test-key"),
        patch.object(routes.config, "SKIP_LOGIN_SUBNETS", []),
    ):
        with app.test_request_context(
            "/protected", headers={"X-API-Key": "matching-test-key"}
        ):
            assert routes.login_required(lambda: "protected")() == "protected"
