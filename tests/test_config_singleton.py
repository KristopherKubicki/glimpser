"""Tests for config singleton."""
import importlib
import os
import tempfile
import unittest
from unittest.mock import patch


class TestConfigSingleton(unittest.TestCase):
    def test_env_loaded_once_and_engine_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "GLIMPSER_DATABASE_PATH": os.path.join(tmp, "t.db"),
                "GLIMPSER_BACKUP_PATH": os.path.join(tmp, "b.json"),
            }
            with patch.dict(os.environ, env):
                import app.config as config

                importlib.reload(config)

                with patch.object(config, "load_dotenv") as ld:
                    config._DOTENV_LOADED = False
                    config._load_dotenv_once()
                    config._load_dotenv_once()
                    self.assertEqual(ld.call_count, 1)

                config._engine = None
                config.SessionLocal = None

                session1 = config._get_session()
                engine_id = id(config._engine)
                session1.close()

                session2 = config._get_session()
                session2_engine_id = id(config._engine)
                session2.close()

                self.assertEqual(engine_id, session2_engine_id)

                importlib.reload(config)


if __name__ == "__main__":
    unittest.main()
