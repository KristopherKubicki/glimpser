import argparse
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import call, patch

import app.config as config  # noqa: E402
import generate_credentials  # noqa: E402


class TestGenerateCredentials(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.old_db_path = config.DATABASE_PATH
        config.DATABASE_PATH = os.path.join(self.temp_dir, "test.db")
        self.conn = sqlite3.connect(config.DATABASE_PATH)

        create_settings_table = """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL
        );
        """
        cursor = self.conn.cursor()
        cursor.execute(create_settings_table)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        os.remove(config.DATABASE_PATH)
        config.DATABASE_PATH = self.old_db_path
        os.rmdir(self.temp_dir)

    def test_upsert_setting(self):
        generate_credentials.upsert_setting("test_key", "test_value", self.conn)
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE name='test_key'")
        result = cursor.fetchone()
        self.assertEqual(result[0], "test_value")

        generate_credentials.upsert_setting("test_key", "new_value", self.conn)
        cursor.execute("SELECT value FROM settings WHERE name='test_key'")
        result = cursor.fetchone()
        self.assertEqual(result[0], "new_value")

    def test_create_settings(self):
        generate_credentials.create_settings(self.conn)
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='settings'"
        )
        result = cursor.fetchone()
        self.assertIsNotNone(result)

    def test_create_users(self):
        """The users table should be created if missing."""
        generate_credentials.create_users(self.conn)
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_upsert_user(self):
        """Inserting and updating users should modify the table."""
        generate_credentials.create_users(self.conn)
        generate_credentials.upsert_user("alice", "hash1", "admin", self.conn)
        cursor = self.conn.cursor()
        cursor.execute("SELECT password_hash, role FROM users WHERE username='alice'")
        self.assertEqual(cursor.fetchone(), ("hash1", "admin"))

        generate_credentials.upsert_user("alice", "hash2", "user", self.conn)
        cursor.execute("SELECT password_hash, role FROM users WHERE username='alice'")
        self.assertEqual(cursor.fetchone(), ("hash2", "user"))

    @patch("generate_credentials.logging.info")
    @patch("generate_credentials.sys.stdin.isatty", return_value=True)
    @patch("generate_credentials.generate_password_hash")
    @patch("generate_credentials.secrets.token_hex")
    @patch("generate_credentials.getpass.getpass")
    @patch("generate_credentials.input")
    @patch(
        "generate_credentials.app.config.get_setting",
        side_effect=lambda n, d=None: (
            config.DATABASE_PATH if n == "DATABASE_PATH" else d
        ),
    )
    def test_generate_credentials_interactive(
        self,
        mock_get_setting,
        mock_input,
        mock_getpass,
        mock_token,
        mock_hash,
        mock_isatty,
        mock_log,
    ):
        mock_input.return_value = "testuser"
        mock_getpass.return_value = "testpass"
        mock_token.return_value = "secretkey"
        mock_hash.return_value = "hashed_password"

        generate_credentials.generate_credentials(args=None)

        self.conn.close()
        self.conn = sqlite3.connect(config.DATABASE_PATH)
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM settings WHERE name='USER_NAME'")
        self.assertEqual(cur.fetchone()[0], "testuser")
        cur.execute("SELECT value FROM settings WHERE name='USER_PASSWORD_HASH'")
        self.assertEqual(cur.fetchone()[0], "hashed_password")
        cur.execute("SELECT value FROM settings WHERE name='SECRET_KEY'")
        self.assertEqual(cur.fetchone()[0], "secretkey")
        cur.execute(
            "SELECT username, password_hash FROM users WHERE username='testuser'"
        )
        self.assertEqual(cur.fetchone(), ("testuser", "hashed_password"))

        mock_log.assert_has_calls(
            [
                call("Credentials and settings updated in the database."),
                call(
                    "Open http://%s:%s in your browser after starting Glimpser to finish setup.",
                    config.HOST,
                    config.PORT,
                ),
            ]
        )

    @patch("generate_credentials.generate_password_hash", return_value="h")
    @patch(
        "generate_credentials.app.config.get_setting", side_effect=lambda n, d=None: d
    )
    def test_generate_credentials_args(self, mock_get, mock_hash):
        """Non-interactive credentials creation should populate both tables."""
        generate_credentials.create_settings(self.conn)
        args = argparse.Namespace(
            db_path=config.DATABASE_PATH,
            username="bob",
            password="secret",  # pragma: allowlist secret
            update_password=True,
            secret_key="xyz",  # pragma: allowlist secret
            update_key=True,
        )
        generate_credentials.generate_credentials(args)
        self.conn.close()
        self.conn = sqlite3.connect(config.DATABASE_PATH)
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM settings WHERE name='USER_NAME'")
        self.assertEqual(cur.fetchone()[0], "bob")
        cur.execute("SELECT value FROM settings WHERE name='USER_PASSWORD_HASH'")
        self.assertEqual(cur.fetchone()[0], "h")
        cur.execute("SELECT value FROM settings WHERE name='SECRET_KEY'")
        self.assertEqual(cur.fetchone()[0], "xyz")
        cur.execute("SELECT username, password_hash FROM users WHERE username='bob'")
        self.assertEqual(cur.fetchone(), ("bob", "h"))

    @patch("generate_credentials.generate_password_hash", return_value="pw")
    @patch(
        "generate_credentials.app.config.get_setting", side_effect=lambda n, d=None: d
    )
    def test_update_password_only(self, mock_get, mock_hash):
        """Updating only the password should still modify the users table."""
        generate_credentials.create_settings(self.conn)
        args = argparse.Namespace(
            db_path=config.DATABASE_PATH,
            username=None,
            password="secret",  # pragma: allowlist secret
            update_password=True,
            secret_key=None,
            update_key=False,
        )
        generate_credentials.generate_credentials(args)
        self.conn.close()
        self.conn = sqlite3.connect(config.DATABASE_PATH)
        cur = self.conn.cursor()
        cur.execute("SELECT username, password_hash FROM users WHERE username='admin'")
        self.assertEqual(cur.fetchone(), ("admin", "pw"))

    @patch("generate_credentials.generate_password_hash", return_value="h")
    @patch(
        "generate_credentials.app.config.get_setting", side_effect=lambda n, d=None: d
    )
    def test_update_key_only(self, mock_get, mock_hash):
        """Updating only the secret key should still update the users table."""
        generate_credentials.create_settings(self.conn)
        args = argparse.Namespace(
            db_path=config.DATABASE_PATH,
            username=None,
            password=None,
            update_password=False,
            secret_key="new",  # pragma: allowlist secret
            update_key=True,
        )
        generate_credentials.generate_credentials(args)
        self.conn.close()
        self.conn = sqlite3.connect(config.DATABASE_PATH)
        cur = self.conn.cursor()
        cur.execute("SELECT username FROM users")
        self.assertEqual(cur.fetchone()[0], "admin")


if __name__ == "__main__":
    unittest.main()
