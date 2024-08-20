import secrets
import sqlite3
import getpass

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

def generate_credentials():

    conn = sqlite3.connect(app.config.get_setting("DATABASE_PATH","data/glimpser.db"))

    create_settings(conn)

    # Use existing settings or generate new ones
    secret_key = app.config.get_setting("SECRET_KEY", secrets.token_hex(16)) # this is going to be empty, because the db doesnt exist, but it might be an env
    username = input(
        f"Enter the username for login [{app.config.get_setting('USER_NAME', 'admin')}]: "
    ) or app.config.get_setting("USER_NAME", "admin")
    password = getpass.getpass("Enter the password for login: ")
    password_hash = generate_password_hash(password)

    app.config.USER_NAME = username
    app.config.USER_PASSWORD_HASH = password_hash

    # Connect to the database

    # Update or insert the settings into the database
    upsert_setting("SECRET_KEY", secret_key, conn)
    upsert_setting("USER_NAME", username, conn)
    upsert_setting("USER_PASSWORD_HASH", password_hash, conn)
    upsert_setting(
        "API_KEY", app.config.get_setting("API_KEY", secrets.token_hex(32)), conn
    )
    upsert_setting(
        "CHATGPT_KEY", app.config.get_setting("CHATGPT_KEY", ""), conn
    )  # Placeholder for CHATGPT_KEY

    conn.close()

    print("Credentials generated and stored in the database.")

    # TODO: consider adding some test cameras for this user


if __name__ == "__main__":
    generate_credentials()

