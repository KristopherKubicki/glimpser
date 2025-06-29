"""Tests for routes more."""
import os
import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402

from app.routes import TemplateName, get_active_groups, update_setting  # noqa: E402


class TestTemplateName(unittest.TestCase):
    def test_valid_name(self):
        tn = TemplateName("cam1")
        self.assertEqual(str(tn), "cam1")
        self.assertEqual(repr(tn), "TemplateName('cam1')")

    def test_invalid_name(self):
        with self.assertRaises(ValueError):
            TemplateName("bad name")

    def test_validate_static(self):
        self.assertTrue(TemplateName.validate("valid"))
        self.assertFalse(TemplateName.validate("not valid"))


class TestGetActiveGroups(unittest.TestCase):
    @patch("app.routes.template_manager.get_templates")
    def test_get_active_groups(self, mock_get_templates):
        mock_get_templates.return_value = {
            1: {"name": "cam1", "groups": "a, b"},
            2: {"name": "cam2", "groups": "b,c"},
            3: {"name": None, "groups": "d"},
        }
        result = get_active_groups()
        self.assertEqual(result, ["a", "b", "c"])
        from app.routes import active_groups

        self.assertEqual(active_groups, ["a", "b", "c"])


class DummySession:
    def __init__(self, existing=None):
        self.existing = existing
        self.inserted = None
        self.updated = None
        self.committed = False

    def execute(self, query, params):
        if "SELECT" in str(query):

            class Cursor:
                def fetchone(self_inner):
                    return (self.existing,) if self.existing is not None else None

            return Cursor()
        if "UPDATE" in str(query):
            self.updated = params
        if "INSERT" in str(query):
            self.inserted = params

            class Result:
                def fetchone(self_inner):
                    return None

            return Result()

        class Default:
            def fetchone(self_inner):
                return None

        return Default()

    def commit(self):
        self.committed = True

    def close(self):
        pass


class TestUpdateSetting(unittest.TestCase):
    @patch("app.routes.restart_server")
    @patch("app.routes.SessionLocal")
    def test_insert_new_setting(self, mock_sessionlocal, mock_restart):
        session = DummySession(existing=None)
        mock_sessionlocal.return_value = session
        self.assertTrue(update_setting("NEW", "1"))
        self.assertIsNotNone(session.inserted)
        mock_restart.assert_called_once()

    @patch("app.routes.restart_server")
    @patch("app.routes.SessionLocal")
    def test_update_existing_changed(self, mock_sessionlocal, mock_restart):
        session = DummySession(existing="1")
        mock_sessionlocal.return_value = session
        self.assertTrue(update_setting("EXIST", "2"))
        self.assertIsNotNone(session.updated)
        mock_restart.assert_called_once()

    @patch("app.routes.restart_server")
    @patch("app.routes.SessionLocal")
    def test_update_existing_same(self, mock_sessionlocal, mock_restart):
        session = DummySession(existing="1")
        mock_sessionlocal.return_value = session
        self.assertTrue(update_setting("EXIST", "1"))
        self.assertIsNone(session.updated)
        mock_restart.assert_not_called()

    def test_invalid_name_returns_false(self):
        self.assertFalse(update_setting("bad name", "1"))


if __name__ == "__main__":
    unittest.main()
