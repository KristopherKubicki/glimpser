import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.template_manager import TemplateManager, Template


class TestTemplateManager(unittest.TestCase):
    def setUp(self):
        self.template_manager = TemplateManager()

    def tearDown(self):
        # Clean up any resources after each test if needed
        pass

    @patch("app.utils.template_manager.SessionLocal")
    def test_get_templates(self, mock_session):
        # Mock the session and query
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_query = mock_session_instance.query.return_value
        mock_all = mock_query.all

        # Create some mock templates
        mock_template1 = Template(name="template1", frequency=60)
        mock_template2 = Template(name="template2", frequency=120)
        mock_all.return_value = [mock_template1, mock_template2]

        # Call the method
        result = self.template_manager.get_templates()

        # Assert the result
        self.assertEqual(len(result), 2)
        self.assertIn("template1", result)
        self.assertIn("template2", result)
        self.assertEqual(result["template1"]["frequency"], 60)
        self.assertEqual(result["template2"]["frequency"], 120)

    @patch("app.utils.template_manager.SessionLocal")
    def test_save_template(self, mock_session):
        # Mock the session and query
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_query = mock_session_instance.query.return_value
        mock_filter_by = mock_query.filter_by
        mock_first = mock_filter_by.return_value.first

        # Test creating a new template
        mock_first.return_value = None
        template_details = {"name": "new_template", "frequency": 30, "timeout": 5}
        self.template_manager.save_template("new_template", template_details)

        # Assert that a new Template was added to the session
        mock_session_instance.add.assert_called_once()
        mock_session_instance.commit.assert_called_once()

        # Test updating an existing template
        mock_existing_template = MagicMock()
        mock_first.return_value = mock_existing_template
        template_details = {"name": "existing_template", "frequency": 60, "timeout": 10}
        self.template_manager.save_template("existing_template", template_details)

        # Assert that the existing template was updated
        self.assertEqual(mock_existing_template.name, "existing_template")
        self.assertEqual(mock_existing_template.frequency, 60)
        self.assertEqual(mock_existing_template.timeout, 10)
        mock_session_instance.commit.assert_called()

    @patch("app.utils.template_manager.SessionLocal")
    def test_get_template(self, mock_session):
        # Mock the session and query
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_query = mock_session_instance.query.return_value
        mock_filter_by = mock_query.filter_by
        mock_first = mock_filter_by.return_value.first

        # Test getting an existing template
        mock_template = Template(name="test_template", frequency=90)
        mock_first.return_value = mock_template

        result = self.template_manager.get_template("test_template")

        self.assertEqual(result["name"], "test_template")
        self.assertEqual(result["frequency"], 90)

        # Test getting a non-existent template
        mock_first.return_value = None

        result = self.template_manager.get_template("non_existent")

        self.assertEqual(result, {})

    @patch("app.utils.template_manager.SessionLocal")
    def test_delete_template(self, mock_session):
        # Mock the session and query
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_query = mock_session_instance.query.return_value
        mock_filter_by = mock_query.filter_by
        mock_first = mock_filter_by.return_value.first

        # Test deleting an existing template
        mock_template = MagicMock()
        mock_first.return_value = mock_template

        result = self.template_manager.delete_template("existing_template")

        self.assertTrue(result)
        mock_session_instance.delete.assert_called_once_with(mock_template)
        mock_session_instance.commit.assert_called_once()

        # Test deleting a non-existent template
        mock_first.return_value = None

        result = self.template_manager.delete_template("non_existent")

        self.assertFalse(result)
        mock_session_instance.delete.assert_called_once()  # Should not be called again
        mock_session_instance.commit.assert_called_once()  # Should not be called again


if __name__ == "__main__":
    unittest.main()
