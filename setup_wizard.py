#!/usr/bin/env python3
"""Interactive setup wizard for first-time Glimpser installs."""

from __future__ import annotations

import argparse
import os
import secrets
import sqlite3
from typing import Any

from werkzeug.security import generate_password_hash

import app.config


def create_tables(conn: sqlite3.Connection) -> None:
    """Create database tables if missing."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL
        );
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT
        );
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            frequency INTEGER DEFAULT 60,
            timeout INTEGER DEFAULT 10,
            notes TEXT DEFAULT '',
            motion_filter TEXT DEFAULT '',
            last_caption TEXT DEFAULT '',
            last_caption_time TEXT DEFAULT '',
            last_motion_caption TEXT DEFAULT '',
            last_motion_time TEXT DEFAULT '',
            last_screenshot_time TEXT DEFAULT '',
            last_video_time TEXT DEFAULT '',
            offline_since TEXT DEFAULT '',
            capture_failed BOOLEAN DEFAULT 0,
            object_filter TEXT DEFAULT '',
            object_confidence REAL DEFAULT 0.5,
            popup_xpath TEXT DEFAULT '',
            dedicated_xpath TEXT DEFAULT '',
            callback_url TEXT DEFAULT '',
            proxy TEXT DEFAULT '',
            auth_username TEXT DEFAULT '',
            auth_password TEXT DEFAULT '',
            url TEXT DEFAULT '',
            thumbnail TEXT DEFAULT '',
            groups TEXT DEFAULT '',
            baseline_caption TEXT DEFAULT '',
            invert BOOLEAN DEFAULT 0,
            dark BOOLEAN DEFAULT 0,
            headless BOOLEAN DEFAULT 1,
            stealth BOOLEAN DEFAULT 0,
            browser BOOLEAN DEFAULT 0,
            livecaption BOOLEAN DEFAULT 0,
            danger BOOLEAN DEFAULT 0,
            motion REAL DEFAULT 0.2,
            rollback_frames INTEGER DEFAULT 0
        );
    """
    )
    conn.commit()


def upsert_setting(conn: sqlite3.Connection, name: str, value: str | None) -> None:
    """Insert or update a setting."""
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


def upsert_user(
    conn: sqlite3.Connection, username: str, password_hash: str, role: str
) -> None:
    """Insert or update a user record."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            password_hash=excluded.password_hash,
            role=excluded.role;
    """,
        (username, password_hash, role),
    )
    conn.commit()


def insert_template(conn: sqlite3.Connection, data: dict[str, Any]) -> bool:
    """Insert a template if it doesn't already exist."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM templates WHERE name = ?", (data["name"],))
    if cursor.fetchone()[0] > 0:
        return False
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?" for _ in data])
    query = f"INSERT INTO templates ({columns}) VALUES ({placeholders})"
    cursor.execute(query, list(data.values()))
    conn.commit()
    return True


def create_default_settings(conn: sqlite3.Connection) -> None:
    """Populate settings with sensible defaults."""
    defaults = {
        "NAME": "Glimpser",
        "HOST": "0.0.0.0",
        "PORT": "8082",
        "DEBUG": "False",
        "LOG_LEVEL": "INFO",
        "LOG_COLOR": "True",
        "SESSION_COOKIE_SECURE": "True",
        "SESSION_COOKIE_HTTPONLY": "True",
        "SESSION_TIMEOUT_MINUTES": "30",
        "AUTO_LOGIN_DAYS": "7",
        "MAX_WORKERS": "4",
        "MAX_RAW_DATA_SIZE": str(100 * 1024 * 1024),
        "MAX_IMAGE_RETENTION_AGE": "7",
        "MAX_VIDEO_RETENTION_AGE": "30",
        "NUM_FRAMES": "3",
        "CAPTURE_TIMEOUT": "30",
        "LIVE_FALLBACK_FPS": "1",
        "DEFAULT_CLIP_DURATION": "60",
        "CLOCK_NAVBAR": "True",
        "CLOCK_OVERLAY": "False",
        "HEALTH_STATUS_ALWAYS_VISIBLE": "False",
        "UA": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/135.0.0.0 Safari/537.36"
        ),
        "LANG": "en-US",
        "TZ": "UTC",
        "SCHEDULER_API_ENABLED": "True",
        "DISCOVERY_AUTOSTART": "False",
        "FFMPEG_HWACCEL": "auto",
        "FFMPEG_THREADS": "2",
        "EMAIL_ENABLED": "False",
        "SMS_ENABLED": "False",
        "CAP_ENABLED": "False",
        "ALLOW_BOTS": "False",
        "AUTO_UPDATE_BRANCH": "None",
    }
    for key, value in defaults.items():
        upsert_setting(conn, key, value)


def create_example_templates(conn: sqlite3.Connection) -> int:
    """Insert example templates."""
    templates = [
        {
            "name": "example_abbey_road",
            "url": "https://www.earthcam.com/world/england/london/abbeyroad/",
            "frequency": 5,
            "timeout": 15,
            "notes": "Example: Abbey Road crossing webcam",
            "groups": "examples,public_cams",
            "headless": True,
            "browser": True,
            "stealth": False,
            "livecaption": False,
            "motion": 0.1,
            "object_confidence": 0.7,
        },
        {
            "name": "example_cnn_news",
            "url": "https://cnn.com",
            "frequency": 10,
            "timeout": 30,
            "notes": "Example: CNN news website (requires browser)",
            "groups": "examples,news",
            "headless": True,
            "browser": True,
            "stealth": False,
            "livecaption": True,
            "motion": 0.2,
            "object_confidence": 0.5,
        },
    ]
    count = 0
    for template in templates:
        if insert_template(conn, template):
            count += 1
    return count


def create_directories() -> None:
    """Create required directory structure."""
    dirs = [
        "data",
        "data/screenshots",
        "data/video",
        "data/clips",
        "data/summaries",
        "logs",
    ]
    for directory in dirs:
        os.makedirs(directory, exist_ok=True)


def interactive_setup() -> int:
    """Run the interactive wizard."""
    db_path = app.config.get_setting("DATABASE_PATH", "data/glimpser.db")
    db_path = input(f"Database path [{db_path}]: ") or db_path
    username = input("Admin username [admin]: ") or "admin"
    password = input("Admin password: ")
    api_key = f"glimpser_{secrets.token_hex(8)}"
    create_templates = input("Create example templates? [Y/n]: ").lower() != "n"

    create_directories()
    conn = sqlite3.connect(db_path)
    create_tables(conn)
    create_default_settings(conn)

    password_hash = generate_password_hash(password)
    upsert_user(conn, username, password_hash, "admin")
    upsert_setting(conn, "USER_NAME", username)
    upsert_setting(conn, "USER_PASSWORD_HASH", password_hash)
    upsert_setting(conn, "SECRET_KEY", secrets.token_hex(32))
    upsert_setting(conn, "API_KEY", api_key)

    if create_templates:
        create_example_templates(conn)

    conn.close()
    print("Setup complete. Start Glimpser to begin.")
    return 0


def main() -> int:
    """Entry point for the setup wizard."""
    parser = argparse.ArgumentParser(description="Glimpser setup wizard")
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()

    if args.non_interactive:
        return 1
    return interactive_setup()


if __name__ == "__main__":
    raise SystemExit(main())
