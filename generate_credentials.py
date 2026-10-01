#!/usr/bin/env python3
# generate_credentials.py
"""Create or update Glimpser credentials and settings.

Run the script without arguments to interactively set up the initial
``settings`` and ``users`` tables in the SQLite database. Command-line
options allow specifying the database path, username, password and secret
key, or updating only specific values.
"""

import argparse
import getpass
import logging
import secrets
import sqlite3
import sys

from werkzeug.security import generate_password_hash

import app.config


def upsert_setting(name: str, value: str | None, conn: sqlite3.Connection) -> None:
    """Insert or update a setting in the database.

    Parameters
    ----------
    name : str
        Setting key.
    value : str | None
        Value to store; if ``None`` the function does nothing.
    conn : sqlite3.Connection
        Database connection.
    """
    if value is None:
        return

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO settings (name, value)
        VALUES (?, ?)
        ON CONFLICT(name) DO UPDATE SET value=excluded.value;
    """,
        (name, value),
    )
    conn.commit()


def create_settings(conn: sqlite3.Connection) -> None:
    """Create the ``settings`` table if it is missing.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    """
    create_settings_table = """
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        value TEXT NOT NULL
    );
    """
    cursor = conn.cursor()
    cursor.execute(create_settings_table)
    conn.commit()


def create_users(conn: sqlite3.Connection) -> None:
    """Create the ``users`` table if it is missing.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    """
    create_users_table = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT,
        temp_password_required BOOLEAN DEFAULT 0
    );
    """
    cursor = conn.cursor()
    cursor.execute(create_users_table)
    conn.commit()


def ensure_user_column(
    conn: sqlite3.Connection, column_name: str, column_type: str, default: str
) -> None:
    """Add a column to the users table if it doesn't already exist."""

    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN "
            f"{column_name} {column_type} DEFAULT {default}"
        )
        conn.commit()


def upsert_user(
    username: str,
    password_hash: str,
    role: str,
    conn: sqlite3.Connection,
    temp_password_required: int = 0,
) -> None:
    """Insert or update a user record.

    Parameters
    ----------
    username : str
        Login name for the user.
    password_hash : str
        Hashed password to store.
    role : str
        User role within the application.
    conn : sqlite3.Connection
        Database connection.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (username, password_hash, role, temp_password_required)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            password_hash=excluded.password_hash,
            role=excluded.role,
            temp_password_required=excluded.temp_password_required;
        """,
        (username, password_hash, role, temp_password_required),
    )
    conn.commit()


def generate_credentials(args: argparse.Namespace | None) -> None:
    """Create or update application credentials and settings.

    Parameters
    ----------
    args : argparse.Namespace | None
        Command line arguments. If ``None`` the function prompts interactively.
    """
    # Use the same DB path the application uses. This path is already resolved
    # relative to the project root in `app.config` so it stays stable across
    # restarts even if the working directory changes.
    database_path = app.config.DATABASE_PATH
    if args and args.db_path:
        candidate = args.db_path.strip()
        if candidate:
            # Mirror the `app.config` behavior: treat relative paths as
            # project-root relative.
            base_dir = app.config._BASE_DIR  # internal but stable within this repo
            db_path = (base_dir / candidate).resolve()
            database_path = str(db_path) if not candidate.startswith("/") else candidate

    conn = sqlite3.connect(database_path)

    if args is None or (not args.update_password and not args.update_key):
        create_settings(conn)

    create_users(conn)
    ensure_user_column(conn, "temp_password_required", "BOOLEAN", "0")

    # Determine username early so it is always defined
    username = app.config.get_setting("USER_NAME", "admin")

    # Handle each setting individually
    if args is None:
        if sys.stdin.isatty():
            username = input(f"Enter the username for login [{username}]: ") or username
        upsert_setting("USER_NAME", username.strip(), conn)
    elif args.username is not None:
        if args.username:
            username = args.username
            upsert_setting("USER_NAME", username.strip(), conn)

    updating_password = args is None or args.password or args.update_password
    if updating_password:
        password: str | None = None
        if args and args.password:
            password = args.password
        elif sys.stdin.isatty():
            password = getpass.getpass("Enter the password for login: ")
        else:
            raise RuntimeError(
                "Refusing to generate a random password in non-interactive mode. "
                "Provide --password (and optionally --temp-password) or run "
                "generate_credentials.py in a TTY."
            )

        password = password.strip()
        if not password:
            raise ValueError("Password cannot be empty.")

        password_hash = generate_password_hash(password)
    else:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username.strip(),),
        )
        row = cursor.fetchone()
        password_hash = row[0] if row else ""
        if not password_hash:
            raise RuntimeError(
                "No existing user password found. Provide --password/--update-password "
                "to set an initial password."
            )

    # Remove legacy storage of password hashes in settings.
    try:
        conn.execute("DELETE FROM settings WHERE name = 'USER_PASSWORD_HASH'")
        conn.commit()
    except Exception:
        pass

    if args is None or args.update_key or not args.update_password:
        secret_key = app.config.get_setting("SECRET_KEY", secrets.token_hex(16))
        if args and args.secret_key:
            secret_key = args.secret_key
        upsert_setting("SECRET_KEY", secret_key, conn)

    temp_password_required = None
    if updating_password:
        temp_password_required = (
            1 if args and getattr(args, "temp_password", False) else 0
        )
    if temp_password_required is None:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT temp_password_required FROM users WHERE username = ?",
            (username.strip(),),
        )
        row = cursor.fetchone()
        temp_password_required = int(row[0]) if row else 0

    # Mirror settings into the users table
    upsert_user(
        username.strip(),
        password_hash,
        "admin",
        conn,
        temp_password_required=temp_password_required,
    )

    conn.close()

    logging.info("Updated credentials in database: %s", database_path)
    logging.info("Credentials and settings updated in the database.")
    logging.info(
        "Open http://%s:%s in your browser after starting Glimpser to finish setup.",
        app.config.HOST,
        app.config.PORT,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate or update credentials and settings."
    )
    parser.add_argument("--db-path", type=str, help="Path to the SQLite database file.")
    parser.add_argument("--username", type=str, help="Username for login.")
    parser.add_argument("--password", type=str, help="Password for login.")
    parser.add_argument(
        "--update-password",
        action="store_true",
        help="Update the password only, without creating a new database or changing other settings.",
    )
    parser.add_argument(
        "--secret-key",
        type=str,
        help="Custom secret key. Generates a new one if not provided.",
    )
    parser.add_argument(
        "--temp-password",
        action="store_true",
        help="Mark the provided password as temporary and require reset on next login.",
    )
    parser.add_argument(
        "--update-key", action="store_true", help="Update the secret key."
    )
    args = parser.parse_args()

    generate_credentials(args)
