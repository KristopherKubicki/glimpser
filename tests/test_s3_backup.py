import os
import importlib


def test_backup_config_s3(monkeypatch, tmp_path):
    bucket = "test-bucket"
    backup_path = tmp_path / "config.json"
    db_path = tmp_path / "db.sqlite"

    monkeypatch.setenv("GLIMPSER_S3_BUCKET", bucket)
    monkeypatch.setenv("GLIMPSER_BACKUP_PATH", str(backup_path))
    monkeypatch.setenv("GLIMPSER_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "s")

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE settings (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, value TEXT)")
    conn.execute("INSERT INTO settings (name, value) VALUES ('TEST','value')")
    conn.commit()
    conn.close()

    from app import config
    importlib.reload(config)

    calls = []

    def fake_upload_file(path, key):
        calls.append((path, key))
        return True

    def fake_upload_media_archive():
        calls.append(("media", None))
        return True

    monkeypatch.setattr(config.s3_backup, "upload_file", fake_upload_file)
    monkeypatch.setattr(config.s3_backup, "upload_media_archive", fake_upload_media_archive)

    assert config.backup_config() is True
    assert (str(config.BACKUP_PATH), "config_backup.json") in calls
    assert (str(config.DATABASE_PATH), os.path.basename(str(config.DATABASE_PATH))) in calls
    assert ("media", None) in calls
