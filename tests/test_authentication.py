# tests/test_authentication.py

import unittest

import os
import sys 

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config import USER_NAME, API_KEY
from app.routes import login_required
from app import create_app

class TestAuthentication(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
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
        response = self.client.post(
            "/login",
            data={
                "username": USER_NAME,
                "password": "correct_password",  # Assume this is the correct password
            },
        )
        self.assertEqual(response.status_code, 302)  # Expecting a redirect
        self.assertIn("/index", response.headers["Location"])

    def test_login_failure(self):
        response = self.client.post(
            "/login", data={"username": USER_NAME, "password": "wrong_password"}
        )
        self.assertEqual(
            response.status_code, 200
        )  # Expecting to stay on the login page
        self.assertIn(b"Invalid username or password", response.data)

    def test_logout(self):
        # First, log in
        self.client.post(
            "/login", data={"username": USER_NAME, "password": "correct_password"}
        )
        # Then, logout
        response = self.client.get("/logout")
        self.assertEqual(response.status_code, 302)  # Expecting a redirect
        self.assertIn("/login", response.headers["Location"])

    def test_login_required_without_login(self):
        response = self.client.get("/protected")
        self.assertEqual(
            response.status_code, 302
        )  # Expecting a redirect to login page
        self.assertIn("/login", response.headers["Location"])

    def test_login_required_with_login(self):
        # First, log in
        self.client.post(
            "/login", data={"username": USER_NAME, "password": "correct_password"}
        )
        # Then, access protected route
        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Protected Content", response.data)

    def test_login_required_with_api_key(self):
        response = self.client.get("/protected", headers={"X-API-Key": API_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Protected Content", response.data)


if __name__ == "__main__":
    unittest.main()
