import ast
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event, text

ROOT = Path(__file__).resolve().parents[1] / "app" / "utils"


class DatabaseRepairTests(unittest.TestCase):
    def test_child_uses_own_pool_and_parent_still_works(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules):
            for name in ("app", "app.config"):
                sys.modules[name] = types.ModuleType(name)
            sys.modules["app.config"].DATABASE_PATH = str(Path(directory) / "test.db")
            spec = importlib.util.spec_from_file_location("repair_db", ROOT / "db.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            @event.listens_for(module.engine, "connect")
            def tag_connection(connection, record):
                record.info["pid"] = os.getpid()

            module.engine.dispose()
            with module.engine.begin() as connection:
                connection.execute(text("CREATE TABLE witness(value INTEGER)"))
                connection.execute(text("INSERT INTO witness VALUES(7)"))
            parent_pool = module.engine.pool
            read_fd, write_fd = os.pipe()
            pid = os.fork()
            if pid == 0:
                os.close(read_fd)
                try:
                    with module.engine.connect() as connection:
                        result = {
                            "owner": connection.info["pid"],
                            "pid": os.getpid(),
                            "pool_replaced": module.engine.pool is not parent_pool,
                            "value": connection.execute(
                                text("SELECT value FROM witness")
                            ).scalar(),
                        }
                    os.write(write_fd, json.dumps(result).encode())
                finally:
                    os._exit(0)
            os.close(write_fd)
            with os.fdopen(read_fd) as handle:
                result = json.loads(handle.read())
            _, status = os.waitpid(pid, 0)
            self.assertEqual(status, 0)
            self.assertEqual(result["owner"], result["pid"])
            self.assertTrue(result["pool_replaced"])
            self.assertEqual(result["value"], 7)
            self.assertIs(module.engine.pool, parent_pool)
            with module.engine.begin() as connection:
                self.assertEqual(connection.info["pid"], os.getpid())
                connection.execute(text("INSERT INTO witness VALUES(8)"))
            module.engine.dispose()

    def pressure_functions(self):
        tree = ast.parse((ROOT / "video_archiver.py").read_text())
        functions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"_archive_io_pressure_high", "archive_screenshots"}
        ]
        namespace = {"logging": types.SimpleNamespace(info=lambda *args: None)}
        exec(
            compile(ast.Module(body=functions, type_ignores=[]), "archiver", "exec"),
            namespace,
        )
        return namespace

    def test_pressure_threshold_and_unavailable(self):
        namespace = self.pressure_functions()
        for reading, expected in [
            ("full avg10=50 avg60=10.00 avg300=1 total=5", True),
            ("full avg10=50 avg60=9.99 avg300=1 total=5", False),
            ("some avg10=99 avg60=99 avg300=99 total=5", False),
            ("full avg60=invalid", False),
        ]:
            with (
                self.subTest(reading=reading),
                patch("builtins.open", return_value=io.StringIO(reading)),
            ):
                self.assertEqual(namespace["_archive_io_pressure_high"](), expected)
        with patch("builtins.open", side_effect=FileNotFoundError):
            self.assertFalse(namespace["_archive_io_pressure_high"]())

    def test_deferral_leaves_archive_cursor_untouched(self):
        namespace = self.pressure_functions()
        namespace["_archive_io_pressure_high"] = lambda: True
        # No filesystem/encoder globals: touching the cursor or frames would fail.
        self.assertIsNone(namespace["archive_screenshots"]())

    def test_normal_pressure_reaches_existing_archive_path(self):
        namespace = self.pressure_functions()
        namespace["_archive_io_pressure_high"] = lambda: False

        class ReachedArchive(Exception):
            pass

        def enter_archive(*args, **kwargs):
            raise ReachedArchive

        namespace["os"] = types.SimpleNamespace(makedirs=enter_archive)
        namespace["VIDEO_DIRECTORY"] = "unused"
        with self.assertRaises(ReachedArchive):
            namespace["archive_screenshots"]()


if __name__ == "__main__":
    unittest.main()
