#!/usr/bin/env python3
# generate_credentials.py

import secrets
import sqlite3
import getpass
import argparse
import sys

import app.config
import logging
from werkzeug.security import generate_password_hash


def upsert_setting(name, value, conn):
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


def create_settings(conn):
    create_settings_table = '''
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        value TEXT NOT NULL
    );
    '''
    cursor = conn.cursor()
    cursor.execute(create_settings_table)
    conn.commit()


def create_users(conn):
    create_users_table = '''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT
    );
    '''
    cursor = conn.cursor()
    cursor.execute(create_users_table)
    conn.commit()


def upsert_user(username, password_hash, role, conn):
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


def generate_credentials(args):
    # Use the provided or default database path
    database_path = app.config.get_setting("DATABASE_PATH", "data/glimpser.db")
    if args and args.db_path:
        database_path = args.db_path

    conn = sqlite3.connect(database_path)

    if args is None or (not args.update_password and not args.update_key):
        create_settings(conn)

    create_users(conn)

    # Handle each setting individually
    if args is None or args.username:
        username = app.config.get_setting("USER_NAME", "admin")
        if args:
            username = args.username
        else:
            if sys.stdin.isatty():
                username = input(
                    f"Enter the username for login [{app.config.get_setting('USER_NAME', 'admin')}]: "
                ) or app.config.get_setting("USER_NAME", "admin")
            else:
                username = app.config.get_setting("USER_NAME", "admin")
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
