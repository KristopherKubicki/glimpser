import sqlite3
import app.config


def migrate():
    """Create roles table and add default roles."""
    db_path = app.config.DATABASE_PATH
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
        """
    )
    cur.executemany(
        "INSERT OR IGNORE INTO roles (name) VALUES (?)",
        [("admin",), ("viewer",)],
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
