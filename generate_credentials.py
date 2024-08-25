#!env/bin/python3
# generate_credentials.py

import secrets
import sqlite3
import getpass
import argparse
import sys

import app.config
from werkzeug.security import generate_password_hash


def upsert_setting(name, value, conn):
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


def generate_credentials(args):
    # Use the provided or default database path
    database_path = app.config.get_setting("DATABASE_PATH", "data/glimpser.db")
    if args and args.db_path:
        database_path = args.db_path

    conn = sqlite3.connect(database_path)

    if args is None or (not args.update_password and not args.update_key and not args.update_chatgpt_key):
        create_settings(conn)

    # Handle each setting individually
    if args is None or args.username:
        username = app.config.get_setting("USER_NAME", "admin")
        if args:
            username = args.username
        else:
            if sys.stdin.isatty():
                username = input(f"Enter the username for login [{app.config.get_setting('USER_NAME', 'admin')}]: ") or app.config.get_setting("USER_NAME", "admin")
            else:
                username = app.config.get_setting("USER_NAME", "admin")

        upsert_setting("USER_NAME", username, conn)

    if args is None or args.password or args.update_password:
        password = "" # maybe populate with garbage
        if args:
            password = args.password
        else:
            if sys.stdin.isatty():
                password = getpass.getpass("Enter the password for login: ")
            else:
                password = secrets.token_hex(16)
                # your password is here.  This is the only time youll be able to see it again 

        password_hash = generate_password_hash(password)
        upsert_setting("USER_PASSWORD_HASH", password_hash, conn)

    if args is None or args.update_key or not args.update_password:
        secret_key = app.config.get_setting("SECRET_KEY", secrets.token_hex(16))
        if args:
             secret_key = args.secret_key
        upsert_setting("SECRET_KEY", secret_key, conn)

    if args and args.api_key:
        # TODO: is this right?  we might have to modify or improve this 
        # probably should validate...
        upsert_setting("API_KEY", args.api_key, conn)
    if args is None:
        upsert_setting("API_KEY", secrets.token_hex(32), conn)

    conn.close()

    print("Credentials and settings updated in the database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate or update credentials and settings.")
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to the SQLite database file."
    )
    parser.add_argument(
        "--username",
        type=str,
        help="Username for login."
    )
    parser.add_argument(
        "--password",
        type=str,
        help="Password for login."
    )
    parser.add_argument(
        "--update-password",
        action="store_true",
        help="Update the password only, without creating a new database or changing other settings."
    )
    parser.add_argument(
        "--secret-key",
        type=str,
        help="Custom secret key. Generates a new one if not provided."
    )
    parser.add_argument(
        "--update-key",
        action="store_true",
        help="Update the secret key."
    )
    args = parser.parse_args()

    generate_credentials(args)

