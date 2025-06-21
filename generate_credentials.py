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
        role TEXT
    );
    """
    cursor = conn.cursor()
    cursor.execute(create_users_table)
    conn.commit()


def upsert_user(
    username: str, password_hash: str, role: str, conn: sqlite3.Connection
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
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash, role=excluded.role;
        """,
        (username, password_hash, role),
    )
    conn.commit()


def generate_credentials(args: argparse.Namespace | None) -> None:
    """Create or update application credentials and settings.

    Parameters
    ----------
    args : argparse.Namespace | None
        Command line arguments. If ``None`` the function prompts interactively.
    """
    # Use the provided or default database path
    database_path = app.config.get_setting("DATABASE_PATH", "data/glimpser.db")
    if args and args.db_path:
        database_path = args.db_path

    conn = sqlite3.connect(database_path)

    if args is None or (not args.update_password and not args.update_key):
        create_settings(conn)

    create_users(conn)

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

    if args is None or args.password or args.update_password:
        password = ""  # maybe populate with garbage
        if args:
            password = args.password
        else:
            if sys.stdin.isatty():
                password = getpass.getpass("Enter the password for login: ")
            else:
                password = secrets.token_hex(16)
                # your password is here.  This is the only time youll be able to see it again

        password_hash = generate_password_hash(password.strip())
        upsert_setting("USER_PASSWORD_HASH", password_hash, conn)
    else:
        password_hash = app.config.get_setting("USER_PASSWORD_HASH", "")

    if args is None or args.update_key or not args.update_password:
        secret_key = app.config.get_setting("SECRET_KEY", secrets.token_hex(16))
        if args and args.secret_key:
            secret_key = args.secret_key
        upsert_setting("SECRET_KEY", secret_key, conn)

    # Mirror settings into the users table
    upsert_user(username.strip(), password_hash, "admin", conn)

    conn.close()

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
        "--update-key", action="store_true", help="Update the secret key."
    )
    args = parser.parse_args()

    generate_credentials(args)
