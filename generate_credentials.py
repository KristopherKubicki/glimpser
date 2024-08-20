import secrets
import sqlite3

from app import config
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


def generate_credentials():
    # Use existing settings or generate new ones
    secret_key = config.get_setting("SECRET_KEY", secrets.token_hex(16))
    username = input(
        f"Enter the username for login [{config.get_setting('USER_NAME', 'admin')}]: "
    ) or config.get_setting("USER_NAME", "admin")
    password = input("Enter the password for login: ")
    password_hash = generate_password_hash(password)

    # Connect to the database
    conn = sqlite3.connect(config.DATABASE_PATH)

    # Update or insert the settings into the database
    upsert_setting("SECRET_KEY", secret_key, conn)
    upsert_setting("USER_NAME", username, conn)
    upsert_setting("USER_PASSWORD_HASH", password_hash, conn)
    upsert_setting(
        "API_KEY", config.get_setting("API_KEY", secrets.token_hex(32)), conn
    )
    upsert_setting(
        "CHATGPT_KEY", config.get_setting("CHATGPT_KEY", ""), conn
    )  # Placeholder for CHATGPT_KEY

    conn.close()

    print("Credentials generated and stored in the database.")

    # TODO: consider adding some test cameras for this user


if __name__ == "__main__":
    generate_credentials()
