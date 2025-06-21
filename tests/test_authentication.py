# tests/test_authentication.py

import datetime
import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import create_app
from app.config import USER_NAME
from app.routes import login_required


class TestAuthentication(unittest.TestCase):
    def setUp(self):
        self.app = create_app(enable_watchdog=False, schedule=False, log_cache=False)
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

        # Create a test route protected by login_required
        @self.app.route("/protected")
        @login_required
        def protected():
            return "Protected Content"

    def tearDown(self):
        self.app_context.pop()

    def test_login_success(self):
        with (
            patch("app.routes.SessionLocal") as mock_session_local,
            patch("app.routes.login_attempts", {}),
            patch("app.routes.check_password_hash", return_value=True),
        ):
            dummy_user = SimpleNamespace(id=1, username=USER_NAME, password_hash="hash")

            class DummyQuery:
                def filter_by(self, **kwargs):
                    return self

                def first(self):
                    return dummy_user

            class DummySession:
                def query(self, model):
                    return DummyQuery()

                def close(self):
                    pass

            mock_session_local.return_value = DummySession()

            response = self.client.post(
                "/login",
                data={
                    "username": USER_NAME,
                    "password": "correct_password",  # pragma: allowlist secret
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertIn("/", response.headers["Location"])

    def test_login_redirects_to_next_when_safe(self):
        with (
            patch("app.routes.SessionLocal") as mock_session_local,
            patch("app.routes.login_attempts", {}),
            patch("app.routes.check_password_hash", return_value=True),
        ):
            dummy_user = SimpleNamespace(id=1, username=USER_NAME, password_hash="hash")

            class DummyQuery:
                def filter_by(self, **kwargs):
                    return self

                def first(self):
                    return dummy_user

            class DummySession:
                def query(self, model):
                    return DummyQuery()

                def close(self):
                    pass

            mock_session_local.return_value = DummySession()

            response = self.client.post(
                "/login?next=/protected",
                data={
                    "username": USER_NAME,
                    "password": "correct_password",  # pragma: allowlist secret
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual("/protected", response.headers["Location"])

    def test_login_redirects_ignores_unsafe_next(self):
        with (
            patch("app.routes.SessionLocal") as mock_session_local,
            patch("app.routes.login_attempts", {}),
            patch("app.routes.check_password_hash", return_value=True),
        ):
            dummy_user = SimpleNamespace(id=1, username=USER_NAME, password_hash="hash")

            class DummyQuery:
                def filter_by(self, **kwargs):
                    return self

                def first(self):
                    return dummy_user

            class DummySession:
                def query(self, model):
                    return DummyQuery()

                def close(self):
                    pass

            mock_session_local.return_value = DummySession()

            response = self.client.post(
                "/login?next=http://evil.com",
                data={
                    "username": USER_NAME,
                    "password": "correct_password",  # pragma: allowlist secret
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual("/", response.headers["Location"])

    def test_login_failure(self):
        with (
            patch("app.routes.SessionLocal") as mock_session_local,
            patch("app.routes.check_password_hash", return_value=False),
        ):
            dummy_user = SimpleNamespace(id=1, username=USER_NAME, password_hash="hash")

            class DummyQuery:
                def filter_by(self, **kwargs):
                    return self

                def first(self):
                    return dummy_user

            class DummySession:
                def query(self, model):
                    return DummyQuery()

                def close(self):
                    pass

            mock_session_local.return_value = DummySession()

            response = self.client.post(
                "/login",
                data={
                    "username": USER_NAME,
                    "password": "wrong_password",  # pragma: allowlist secret
                },
            )
            self.assertEqual(response.status_code, 200)

    def test_login_failure_lockout(self):
        # Simulate multiple failed login attempts to trigger lockout
        login_attempts = {}  # reset
        for _ in range(5):  # Assuming lockout occurs after 5 attempts
            with (
                patch("app.routes.SessionLocal") as mock_session_local,
                patch("app.routes.check_password_hash", return_value=False),
            ):
                dummy_user = SimpleNamespace(
                    id=1,
                    username=USER_NAME,
                    password_hash="hash",  # pragma: allowlist secret
                )

                class DummyQuery:
                    def filter_by(self, **kwargs):
                        return self

                    def first(self):
                        return dummy_user

                class DummySession:
                    def query(self, model):
                        return DummyQuery()

                    def close(self):
                        pass

                mock_session_local.return_value = DummySession()
                self.client.post(
                    "/login",
                    data={
                        "username": USER_NAME,
                        "password": "wrong_password",  # pragma: allowlist secret
                    },
                )

        with (
            patch("app.routes.SessionLocal") as mock_session_local,
            patch("app.routes.check_password_hash", return_value=False),
        ):
            dummy_user = SimpleNamespace(id=1, username=USER_NAME, password_hash="hash")

            class DummyQuery:
                def filter_by(self, **kwargs):
                    return self

                def first(self):
                    return dummy_user

            class DummySession:
                def query(self, model):
                    return DummyQuery()

                def close(self):
                    pass

            mock_session_local.return_value = DummySession()
            response = self.client.post(
                "/login",
                data={
                    "username": USER_NAME,
                    "password": "wrong_password",  # pragma: allowlist secret
                },
            )
        self.assertEqual(response.status_code, 429)  # Expecting lockout response
        login_attempts = {}  # reset

    def test_logout(self):
        login_attempts = {}  # reset
        with (
            patch("app.routes.SessionLocal") as mock_session_local,
            patch("app.routes.check_password_hash", return_value=True),
        ):
            dummy_user = SimpleNamespace(id=1, username=USER_NAME, password_hash="hash")

            class DummyQuery:
                def filter_by(self, **kwargs):
                    return self

                def first(self):
                    return dummy_user

            class DummySession:
                def query(self, model):
                    return DummyQuery()

                def close(self):
                    pass

            mock_session_local.return_value = DummySession()
            self.client.post(
                "/login",
                data={
                    "username": USER_NAME,
                    "password": "correct_password",  # pragma: allowlist secret
                },
            )
        response = self.client.get("/logout")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_login_required_without_login(self):
        login_attempts = {}  # reset
        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_login_required_with_login(self):
        login_attempts = {}  # reset
        dummy_user = SimpleNamespace(id=1, username=USER_NAME)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        with (
            patch("app.routes.session", {"user_id": 1}),
            patch("app.routes.SessionLocal", return_value=DummySession()),
        ):
            response = self.client.get("/protected")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Protected Content", response.data)

    def test_login_required_with_expired_session(self):
        login_attempts = {}  # reset
        # Set an expiry date that is in the past
        expired_time = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        dummy_user = SimpleNamespace(id=1, username=USER_NAME)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        with (
            patch("app.routes.session", {"user_id": 1, "expiry": expired_time}),
            patch("app.routes.SessionLocal", return_value=DummySession()),
        ):
            response = self.client.get("/protected")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.headers["Location"])

    def test_login_required_refreshes_expiry(self):
        login_attempts = {}  # reset
        initial_expiry = (
            datetime.datetime.now() + datetime.timedelta(minutes=5)
        ).strftime("%Y-%m-%d %H:%M:%S")
        session_data = {"user_id": 1, "expiry": initial_expiry}
        dummy_user = SimpleNamespace(id=1, username=USER_NAME)

        class DummyQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return dummy_user

        class DummySession:
            def query(self, model):
                return DummyQuery()

            def close(self):
                pass

        with (
            patch("app.routes.session", session_data),
            patch("app.routes.SessionLocal", return_value=DummySession()),
        ):
            response = self.client.get("/protected")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Protected Content", response.data)
            self.assertNotEqual(session_data["expiry"], initial_expiry)
            new_ts = datetime.datetime.strptime(
                session_data["expiry"], "%Y-%m-%d %H:%M:%S"
            )
            old_ts = datetime.datetime.strptime(initial_expiry, "%Y-%m-%d %H:%M:%S")
            self.assertGreater(new_ts, old_ts)

    def test_login_required_with_api_key(self):
        login_attempts = {}  # reset
        mock_api_key = "mock_api_key_for_testing"  # pragma: allowlist secret
        with patch("app.routes.API_KEY", mock_api_key):
            response = self.client.get(
                "/protected", headers={"X-API-Key": mock_api_key}
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Protected Content", response.data)

            response = self.client.get(
                "/protected", headers={"X-API-Key": "wrong_api_key"}
            )
            self.assertEqual(response.status_code, 401)
            self.assertIn(b"Invalid API key", response.data)

    def test_login_required_with_no_api_key(self):
        login_attempts = {}  # reset
        # Test the behavior when no API key is provided
        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_login_required_with_timed_api_key(self):
        login_attempts = {}  # reset
        mock_timed_key = "mock_timed_key_for_testing"
        with patch("app.routes.is_hash_valid", return_value=True):
            response = self.client.get("/protected?timed_key=" + mock_timed_key)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Protected Content", response.data)

        with patch("app.routes.is_hash_valid", return_value=False):
            response = self.client.get("/protected?timed_key=" + mock_timed_key)
            self.assertEqual(response.status_code, 401)
            self.assertIn(b"Invalid timed key", response.data)

    def test_combined_session_and_api_key(self):
        login_attempts = {}  # reset
        # Test with both session and API key
        mock_api_key = "mock_api_key_for_testing"  # pragma: allowlist secret
        with patch("app.routes.API_KEY", mock_api_key):
            dummy_user = SimpleNamespace(id=1, username=USER_NAME)

            class DummyQuery:
                def filter_by(self, **kwargs):
                    return self

                def first(self):
                    return dummy_user

            class DummySession:
                def query(self, model):
                    return DummyQuery()

                def close(self):
                    pass

            with (
                patch("app.routes.session", {"user_id": 1}),
                patch("app.routes.SessionLocal", return_value=DummySession()),
            ):
                response = self.client.get(
                    "/protected", headers={"X-API-Key": mock_api_key}
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"Protected Content", response.data)

    def test_invalid_session_data(self):
        login_attempts = {}  # reset
        # Test with invalid session data
        with patch("app.routes.session", {"user_id": "not_a_boolean"}):
            response = self.client.get("/protected")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.headers["Location"])

    def test_api_key_security(self):
        login_attempts = {}  # reset
        # Test with a replay attack scenario (using a previously valid API key)
        mock_api_key = "mock_api_key_for_testing"  # pragma: allowlist secret
        with patch("app.routes.API_KEY", mock_api_key):
            response = self.client.get(
                "/protected", headers={"X-API-Key": mock_api_key}
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Protected Content", response.data)

        # Assume API key should now be invalid (e.g., if it was a one-time-use key)
        with patch("app.routes.API_KEY", "another_mock_api_key"):
            response = self.client.get(
                "/protected", headers={"X-API-Key": mock_api_key}
            )
            self.assertEqual(response.status_code, 401)
            self.assertIn(b"Invalid API key", response.data)

    def test_sso_login_success(self):
        login_attempts = {}  # reset
        with (
            patch("app.routes.config.SSO_TOKEN", "secret"),
            patch(
                "app.routes.config.SSO_USERNAME",
                USER_NAME,
            ),
            patch("app.routes.SessionLocal") as mock_session_local,
        ):
            dummy_user = SimpleNamespace(id=1, username=USER_NAME, password_hash="hash")

            class DummyQuery:
                def filter_by(self, **kwargs):
                    return self

                def first(self):
                    return dummy_user

            class DummySession:
                def query(self, model):
                    return DummyQuery()

                def close(self):
                    pass

            mock_session_local.return_value = DummySession()

            response = self.client.get("/sso?token=secret")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/", response.headers["Location"])

    def test_sso_login_invalid(self):
        login_attempts = {}  # reset
        with patch("app.routes.config.SSO_TOKEN", "secret"):
            response = self.client.get("/sso?token=wrong")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.headers["Location"])

    def test_remember_me_session_persistent(self):
        login_attempts = {}
        with (
            patch("app.routes.SessionLocal") as mock_session_local,
            patch("app.routes.login_attempts", login_attempts),
            patch("app.routes.check_password_hash", return_value=True),
            patch("app.routes.config.AUTO_LOGIN_DAYS", 10),
        ):
            dummy_user = SimpleNamespace(id=1, username=USER_NAME, password_hash="hash")

            class DummyQuery:
                def filter_by(self, **kwargs):
                    return self

                def first(self):
                    return dummy_user

            class DummySession:
                def query(self, model):
                    return DummyQuery()

                def close(self):
                    pass

            mock_session_local.return_value = DummySession()
            response = self.client.post(
                "/login",
                data={
                    "username": USER_NAME,
                    "password": "correct_password",  # pragma: allowlist secret
                    "remember": "on",
                },
            )
            self.assertEqual(response.status_code, 302)
            cookie_header = response.headers.get("Set-Cookie")
            self.assertIsNotNone(cookie_header)
            parts = cookie_header.split("Expires=")
            self.assertEqual(len(parts), 2)
            expiry_str = parts[1].split(";")[0]
            expiry = datetime.datetime.strptime(expiry_str, "%a, %d %b %Y %H:%M:%S GMT")
            self.assertGreater(
                expiry, datetime.datetime.utcnow() + datetime.timedelta(days=1)
            )

    def test_sse_unauthorized_message(self):
        login_attempts = {}
        response = self.client.get(
            "/stream_logs",
            headers={"Accept": "text/event-stream"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.mimetype, "text/event-stream")
        self.assertIn(b'{"error": "unauthorized"}', response.data)


if __name__ == "__main__":
    unittest.main()
