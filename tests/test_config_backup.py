import unittest
import os
import sys
import tempfile
import json
import sqlite3
import types
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Minimal SQLAlchemy stub
sqlalchemy_stub = types.ModuleType("sqlalchemy")

def create_engine(url):
    return url.split(':///')[-1]

def text(sql):
    return sql

orm_stub = types.ModuleType("sqlalchemy.orm")

def sessionmaker(autocommit=False, autoflush=False, bind=None):
    def session():
        return sqlite3.connect(bind)
    return session

orm_stub.sessionmaker = sessionmaker
sqlalchemy_stub.create_engine = create_engine
sqlalchemy_stub.text = text
sqlalchemy_stub.orm = orm_stub
sys.modules["sqlalchemy"] = sqlalchemy_stub
sys.modules["sqlalchemy.orm"] = orm_stub

class TestConfigBackup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.backup_path = os.path.join(self.temp_dir.name, "backup.json")

        pkg = types.ModuleType("app")
        pkg.__path__ = [os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))]
        sys.modules["app"] = pkg

        # Ensure config uses our temporary database
        os.environ["GLIMPSER_DATABASE_PATH"] = self.db_path
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "config.py"))
        spec_config = importlib.util.spec_from_file_location("app.config", config_path)
        self.config = importlib.util.module_from_spec(spec_config)
        sys.modules["app.config"] = self.config
        spec_config.loader.exec_module(self.config)

        flask_stub = types.ModuleType("flask")
        for name in ["abort","jsonify","flash","redirect","render_template","request","send_file","send_from_directory","session","url_for","Response"]:
            setattr(flask_stub, name, lambda *a, **k: None)
        sys.modules["flask"] = flask_stub

        pil_stub = types.ModuleType("PIL")
        pil_image_stub = types.ModuleType("PIL.Image")
        pil_stub.Image = pil_image_stub
        sys.modules["PIL"] = pil_stub
        sys.modules["PIL.Image"] = pil_image_stub

        werkzeug_security_stub = types.ModuleType("werkzeug.security")
        werkzeug_security_stub.check_password_hash = lambda x, y: False
        sys.modules["werkzeug.security"] = werkzeug_security_stub
        werkzeug_utils_stub = types.ModuleType("werkzeug.utils")
        werkzeug_utils_stub.secure_filename = lambda x: x
        sys.modules["werkzeug.utils"] = werkzeug_utils_stub

        utils_pkg = types.ModuleType("app.utils")
        sys.modules["app.utils"] = utils_pkg
        db_stub = types.ModuleType("app.utils.db")
        db_stub.SessionLocal = lambda: sqlite3.connect(self.db_path)
        sys.modules["app.utils.db"] = db_stub
        sched_stub = types.ModuleType("app.utils.scheduling")
        sched_stub.log_cache = {}
        sched_stub.log_cache_lock = None
        sys.modules["app.utils.scheduling"] = sched_stub
        sys.modules["app.utils.template_manager"] = types.ModuleType("app.utils.template_manager")
        sys.modules["app.utils.video_archiver"] = types.ModuleType("app.utils.video_archiver")
        sys.modules["app.utils.screenshots"] = types.ModuleType("app.utils.screenshots")

        routes_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "routes.py"))
        spec_routes = importlib.util.spec_from_file_location("app.routes", routes_path)
        self.routes = importlib.util.module_from_spec(spec_routes)
        sys.modules["app.routes"] = self.routes
        spec_routes.loader.exec_module(self.routes)

        self.old_db_path = self.config.DATABASE_PATH
        self.old_backup_path = self.config.BACKUP_PATH
        self.old_session_local = self.config.SessionLocal
        self.old_routes_session_local = self.routes.SessionLocal
        self.old_restart_server = self.routes.restart_server

        self.config.DATABASE_PATH = self.db_path
        self.config.BACKUP_PATH = self.backup_path

        def sqlite_session():
            return sqlite3.connect(self.db_path)

        self.config.SessionLocal = sqlite_session
        self.routes.SessionLocal = sqlite_session
        self.routes.restart_server = lambda: None
        db_stub.SessionLocal = sqlite_session

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.config.DATABASE_PATH = self.old_db_path
        self.config.BACKUP_PATH = self.old_backup_path
        self.config.SessionLocal = self.old_session_local
        self.routes.SessionLocal = self.old_routes_session_local
        self.routes.restart_server = self.old_restart_server
        os.environ.pop("GLIMPSER_DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def test_backup_and_restore(self):
        settings = {
            "SETTING_ONE": "value1",
            "SETTING_TWO": "value2",
            "SETTING_THREE": "value3"
        }

        for name, value in settings.items():
            self.assertTrue(self.routes.update_setting(name, value))

        self.assertTrue(self.config.backup_config())
        self.assertTrue(os.path.exists(self.backup_path))

        with open(self.backup_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data, settings)

        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM settings")
        conn.commit()
        conn.close()

        self.config.restore_config()

        conn = sqlite3.connect(self.db_path)
        restored = dict(conn.execute("SELECT name, value FROM settings").fetchall())
        conn.close()

        self.assertEqual(restored, settings)

if __name__ == "__main__":
    unittest.main()
