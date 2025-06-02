import unittest
import time
import hashlib
import sys
import types
import tempfile
import os
from unittest.mock import patch

# Provide a dummy psutil module if it's not installed
if "psutil" not in sys.modules:
    sys.modules["psutil"] = types.ModuleType("psutil")

if "flask" not in sys.modules:
    flask_mock = types.ModuleType("flask")

    def _dummy(*args, **kwargs):
        return None

    flask_mock.abort = _dummy
    flask_mock.jsonify = lambda *a, **k: {}
    flask_mock.flash = _dummy
    flask_mock.redirect = _dummy
    flask_mock.render_template = _dummy
    flask_mock.request = types.SimpleNamespace(headers={}, args={}, form={})
    flask_mock.send_file = _dummy
    flask_mock.send_from_directory = _dummy
    flask_mock.session = {}
    flask_mock.url_for = lambda *a, **k: ""
    flask_mock.Response = type("Response", (), {})
    flask_mock.Flask = type("Flask", (), {})
    sys.modules["flask"] = flask_mock

if "sqlalchemy" not in sys.modules:
    sqlalchemy_mock = types.ModuleType("sqlalchemy")
    sqlalchemy_mock.text = lambda *a, **k: None
    sys.modules["sqlalchemy"] = sqlalchemy_mock
    sys.modules["sqlalchemy.orm"] = types.ModuleType("sqlalchemy.orm")
    sys.modules["sqlalchemy.orm"].sessionmaker = lambda *a, **k: None

if "werkzeug.security" not in sys.modules:
    ws_mock = types.ModuleType("werkzeug.security")
    ws_mock.check_password_hash = lambda pw_hash, pw: True
    sys.modules["werkzeug.security"] = ws_mock

if "werkzeug.utils" not in sys.modules:
    wu_mock = types.ModuleType("werkzeug.utils")
    wu_mock.secure_filename = lambda x: x
    sys.modules["werkzeug.utils"] = wu_mock

if "PIL" not in sys.modules:
    pil_mock = types.ModuleType("PIL")
    pil_mock.Image = type("Image", (), {})
    sys.modules["PIL"] = pil_mock

if "app.config" not in sys.modules:
    config_mock = types.ModuleType("app.config")
    config_mock.API_KEY = "dummy"
    config_mock.SCREENSHOT_DIRECTORY = ""
    config_mock.USER_NAME = ""
    config_mock.USER_PASSWORD_HASH = ""
    config_mock.VIDEO_DIRECTORY = ""
    config_mock.VERSION = 0
    config_mock.BACKUP_PATH = ""
    config_mock.backup_config = lambda: None
    config_mock.restore_config = lambda: None
    sys.modules["app.config"] = config_mock

# Stub app.utils and submodules used in app.routes
if "app.utils" not in sys.modules:
    utils_pkg = types.ModuleType("app.utils")
    sys.modules["app.utils"] = utils_pkg

for sub in [
    "scheduling",
    "template_manager",
    "video_archiver",
    "screenshots",
    "db",
    "retention_policy",
    "email_alerts",
]:
    mod_name = f"app.utils.{sub}"
    if mod_name not in sys.modules:
        mod = types.ModuleType(mod_name)
        sys.modules[mod_name] = mod
        if sub == "scheduling":
            mod.log_cache = []

            class DummyLock:
                def acquire(self):
                    pass

                def release(self):
                    pass

            mod.log_cache_lock = DummyLock()
            mod.schedule_crawlers = lambda *a, **k: None
            mod.schedule_summarization = lambda *a, **k: None
            mod.scheduler = None
            mod.start_log_caching = lambda: None
        if sub == "db":
            mod.SessionLocal = lambda: None
        if sub == "retention_policy":
            mod.retention_cleanup = lambda *a, **k: None
        if sub == "video_archiver":
            mod.archive_screenshots = lambda *a, **k: None
            mod.compile_to_teaser = lambda *a, **k: None
        if sub == "email_alerts":
            mod.email_alert = lambda *a, **k: None

from app.routes import generate_timed_hash, is_hash_valid, generate_video_stream


class TestRoutesUtils(unittest.TestCase):
    def test_generate_and_validate(self):
        constant_key = "TEST_CONSTANT_KEY"
        with patch("app.routes.API_KEY", constant_key):
            timed_hash = generate_timed_hash()
            # Expect a dot separating hash and timestamp
            self.assertIn(".", timed_hash)
            self.assertEqual(len(timed_hash.split(".")), 2)
            # Should be considered valid immediately after generation
            self.assertTrue(is_hash_valid(timed_hash))

            # Modify the hash portion -> invalid
            hash_part, exp = timed_hash.split(".")
            modified = "x" + hash_part[1:] + "." + exp
            self.assertFalse(is_hash_valid(modified))

            # Expired timestamp -> invalid
            expired_time = str(int(time.time()) - 1)
            expired_digest = hashlib.sha256(
                f"{constant_key}{expired_time}".encode()
            ).hexdigest()
            expired_value = f"{expired_digest}.{expired_time}"
            self.assertFalse(is_hash_valid(expired_value))

            # Malformed strings -> invalid
            self.assertFalse(is_hash_valid("noperiod"))
            self.assertFalse(is_hash_valid("one.two.three"))


class TestGenerateVideoStream(unittest.TestCase):
    def test_generate_video_stream(self):
        """Generator yields chunks and restarts when finished."""

        with tempfile.NamedTemporaryFile(delete=False) as temp:
            chunk1 = b"a" * (1024 * 1024)
            chunk2 = b"b" * (1024 * 1024)
            chunk3 = b"c" * (512 * 1024)
            temp.write(chunk1 + chunk2 + chunk3)
            temp.flush()
            path = temp.name

        gen = generate_video_stream(path)
        try:
            self.assertEqual(next(gen), chunk1)
            self.assertEqual(next(gen), chunk2)
            self.assertEqual(next(gen), chunk3)
            # Generator should restart from the beginning
            self.assertEqual(next(gen), chunk1)
        finally:
            gen.close()
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
