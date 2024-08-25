# tests/test_authentication.py

import unittest

import os
import sys 

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import datetime
import unittest
from unittest.mock import patch
from app.config import USER_NAME, API_KEY
from app.routes import login_required, login_attempts
from app import create_app

class TestAuthentication(unittest.TestCase):
    def setUp(self):
        self.app = create_app(watchdog=False, schedule=False)
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
        with patch("app.routes.login_attempts", {}):  # Reset login attempts to avoid lockout
            response = self.client.post(
                "/login",
                data={
                    "username": USER_NAME,
                    "password": "correct_password",
                },
            )
            self.assertEqual(response.status_code, 200)
            # seems sus... 
            #self.assertIn("/", response.headers["Path"])

    def test_login_failure(self):
        response = self.client.post(
            "/login", data={"username": USER_NAME, "password": "wrong_password"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enter your credentials", response.data)

    def test_login_failure_lockout(self):
        # Simulate multiple failed login attempts to trigger lockout
        login_attempts = {} # reset 
        for _ in range(5):  # Assuming lockout occurs after 5 attempts
            self.client.post("/login", data={"username": USER_NAME, "password": "wrong_password"})

        response = self.client.post("/login", data={"username": USER_NAME, "password": "wrong_password"})
        self.assertEqual(response.status_code, 429)  # Expecting lockout response
        login_attempts = {} # reset 

    def test_logout(self):
        login_attempts = {} # reset 
        self.client.post(
            "/login", data={"username": USER_NAME, "password": "correct_password"}
        )
        response = self.client.get("/logout")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_login_required_without_login(self):
        login_attempts = {} # reset 
        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_login_required_with_login(self):
        login_attempts = {} # reset 
        with patch("app.routes.session", {"logged_in": True}):
            response = self.client.get("/protected")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Protected Content", response.data)

    def test_login_required_with_expired_session(self):
        login_attempts = {} # reset 
        # Set an expiry date that is in the past
        expired_time = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        with patch("app.routes.session", {"logged_in": True, "expiry": expired_time}):
            response = self.client.get("/protected")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.headers["Location"])

    def test_login_required_with_api_key(self):
        login_attempts = {} # reset 
        mock_api_key = "mock_api_key_for_testing"
        with patch("app.routes.API_KEY", mock_api_key):
            response = self.client.get("/protected", headers={"X-API-Key": mock_api_key})
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Protected Content", response.data)

            response = self.client.get("/protected", headers={"X-API-Key": "wrong_api_key"})
            self.assertEqual(response.status_code, 401)
            self.assertIn(b"Invalid API key", response.data)

    def test_login_required_with_no_api_key(self):
        login_attempts = {} # reset 
        # Test the behavior when no API key is provided
        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_login_required_with_timed_api_key(self):
        login_attempts = {} # reset 
        mock_timed_key = "mock_timed_key_for_testing"
        with patch("app.routes.is_hash_valid", return_value=True):
            response = self.client.get("/protected?timed_key=" +  mock_timed_key)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Protected Content", response.data)

        with patch("app.routes.is_hash_valid", return_value=False):
            response = self.client.get("/protected?timed_key=" + mock_timed_key)
            self.assertEqual(response.status_code, 401)
            self.assertIn(b"Invalid timed key", response.data)

    def test_combined_session_and_api_key(self):
        login_attempts = {} # reset 
        # Test with both session and API key
        mock_api_key = "mock_api_key_for_testing"
        with patch("app.routes.API_KEY", mock_api_key):
            with patch("app.routes.session", {"logged_in": True}):
                response = self.client.get("/protected", headers={"X-API-Key": mock_api_key})
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"Protected Content", response.data)

    def test_invalid_session_data(self):
        login_attempts = {} # reset 
        # Test with invalid session data
        with patch("app.routes.session", {"logged_in": "not_a_boolean"}):
            response = self.client.get("/protected")
            # TODO: fix these
            #self.assertEqual(response.status_code, 302)
            #self.assertIn("/login", response.headers["Location"])

    def test_api_key_security(self):
        login_attempts = {} # reset 
        # Test with a replay attack scenario (using a previously valid API key)
        mock_api_key = "mock_api_key_for_testing"
        with patch("app.routes.API_KEY", mock_api_key):
            response = self.client.get("/protected", headers={"X-API-Key": mock_api_key})
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Protected Content", response.data)

        # Assume API key should now be invalid (e.g., if it was a one-time-use key)
        with patch("app.routes.API_KEY", "another_mock_api_key"):
            response = self.client.get("/protected", headers={"X-API-Key": mock_api_key})
            self.assertEqual(response.status_code, 401)
            self.assertIn(b"Invalid API key", response.data)

if __name__ == "__main__":
    unittest.main()

