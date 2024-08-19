import os
import unittest

from app.utils.template_manager import TemplateManager


class TestTemplateManager(unittest.TestCase):
    def setUp(self):
        self.template_manager = TemplateManager()

    def test_template_operations(self):
        # Test saving a template
        self.template_manager.save_template("test", {"url": "https://example.com"})
        templates = self.template_manager.get_templates()
        self.assertIn("test", templates)

        # Test retrieving templates
        retrieved_template = templates["test"]
        self.assertEqual(retrieved_template["url"], "https://example.com")

        # Test deleting a template
        self.assertTrue(self.template_manager.delete_template("test"))
        templates = self.template_manager.get_templates()
        self.assertNotIn("test", templates)

    def tearDown(self):
        if os.path.exists(self.test_filepath):
            os.remove(self.test_filepath)


if __name__ == "__main__":
    unittest.main()
