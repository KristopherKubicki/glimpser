import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.template_manager import TemplateManager


class TestTemplateManager(unittest.TestCase):
    def setUp(self):
        self.template_manager = TemplateManager()

    @patch("app.utils.template_manager.SessionLocal")
    def test_get_templates(self, mock_session):
        # Mock the session and query
        mock_query = MagicMock()
        mock_session.return_value.__enter__.return_value.query.return_value = mock_query

        # Mock the query results
        mock_template1 = MagicMock(
            name="template1", __dict__={"id": 1, "name": "Template 1"}
        )
        mock_template2 = MagicMock(
            name="template2", __dict__={"id": 2, "name": "Template 2"}
        )
        mock_query.all.return_value = [mock_template1, mock_template2]

        # Call the method
        result = self.template_manager.get_templates()

        # Assert the result
        expected_result = {
            "template1": {"id": 1, "name": "Template 1"},
            "template2": {"id": 2, "name": "Template 2"},
        }
        self.assertEqual(result, expected_result)

    @patch("app.utils.template_manager.SessionLocal")
    def test_save_template(self, mock_session):
        # Mock the session and query
        mock_query = MagicMock()
        mock_session.return_value.__enter__.return_value.query.return_value = mock_query

        # Mock the query results
        mock_template = MagicMock(name="test_template")
        mock_query.filter_by.return_value.first.return_value = mock_template

        # Call the method
        template_name = "test_template"
        template_details = {"frequency": 30, "timeout": 5}
        self.template_manager.save_template(template_name, template_details)

        # Assert that the template was updated
        mock_template.frequency.assert_called_with(30)
        mock_template.timeout.assert_called_with(5)
        mock_session.return_value.__enter__.return_value.commit.assert_called_once()

    @patch("app.utils.template_manager.SessionLocal")
    def test_get_template(self, mock_session):
        # Mock the session and query
        mock_query = MagicMock()
        mock_session.return_value.__enter__.return_value.query.return_value = mock_query

        # Mock the query results
        mock_template = MagicMock(
            name="test_template", __dict__={"id": 1, "name": "Test Template"}
        )
        mock_query.filter_by.return_value.first.return_value = mock_template

        # Call the method
        result = self.template_manager.get_template("test_template")

        # Assert the result
        expected_result = {"id": 1, "name": "Test Template"}
        self.assertEqual(result, expected_result)

    @patch("app.utils.template_manager.SessionLocal")
    def test_delete_template(self, mock_session):
        # Mock the session and query
        mock_query = MagicMock()
        mock_session.return_value.__enter__.return_value.query.return_value = mock_query

        # Mock the query results
        mock_template = MagicMock(name="test_template")
        mock_query.filter_by.return_value.first.return_value = mock_template

        # Call the method
        result = self.template_manager.delete_template("test_template")

        # Assert the result
        self.assertTrue(result)
        mock_session.return_value.__enter__.return_value.delete.assert_called_once_with(
            mock_template
        )
        mock_session.return_value.__enter__.return_value.commit.assert_called_once()

    @patch("app.utils.template_manager.SessionLocal")
    def test_get_template_by_id(self, mock_session):
        # Mock the session and query
        mock_query = MagicMock()
        mock_session.return_value.__enter__.return_value.query.return_value = mock_query

        # Mock the query results
        mock_template = MagicMock(
            name="test_template", __dict__={"id": 1, "name": "Test Template"}
        )
        mock_query.filter_by.return_value.first.return_value = mock_template

        # Call the method
        result = self.template_manager.get_template_by_id(1)

        # Assert the result
        expected_result = {"id": 1, "name": "Test Template"}
        self.assertEqual(result, expected_result)


if __name__ == "__main__":
    unittest.main()
