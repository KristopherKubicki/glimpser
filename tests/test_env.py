import unittest
import os
import tempfile
import sys
from unittest.mock import patch, mock_open

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.screenshots import is_private_ip
from app.utils.screenshots import remove_background
from app.utils.retention_policy import get_files_sorted_by_creation_time

class TestEnvironmentVariables(unittest.TestCase):

    @patch.dict(os.environ, {"TEST_ENV_VAR": "12345"})
    def test_environment_variable_exists(self):
        self.assertEqual(os.getenv("TEST_ENV_VAR"), "12345")

    @patch.dict(os.environ, {"TEST_ENV_VAR": "12345"})
    def test_environment_variable_missing(self):
        self.assertIsNone(os.getenv("NON_EXISTENT_VAR"))

class TestFileIO(unittest.TestCase):

    @patch("builtins.open", new_callable=mock_open, read_data="data")
    def test_file_reading(self, mock_file):
        with open("fakefile.txt") as file:
            result = file.read()
        mock_file.assert_called_with("fakefile.txt")
        self.assertEqual(result, "data")

    @patch("builtins.open", new_callable=mock_open)
    def test_file_writing(self, mock_file):
        with open("fakefile.txt", "w") as file:
            file.write("new data")
        mock_file.assert_called_with("fakefile.txt", "w")
        mock_file().write.assert_called_once_with("new data")

    def test_temporary_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"temporary data")
            temp_file_path = temp_file.name

        with open(temp_file_path, "rb") as file:
            data = file.read()
        self.assertEqual(data, b"temporary data")

        os.remove(temp_file_path)

class TestStringProcessing(unittest.TestCase):

    def test_string_contains(self):
        string = "This is a test string"
        self.assertIn("test", string)
        self.assertNotIn("missing", string)

    def test_string_split(self):
        string = "apple,banana,orange"
        result = string.split(",")
        self.assertEqual(result, ["apple", "banana", "orange"])

    def test_string_upper(self):
        string = "hello"
        result = string.upper()
        self.assertEqual(result, "HELLO")

    def test_string_strip(self):
        string = "  Hello, World!  "
        result = string.strip()
        self.assertEqual(result, "Hello, World!")
        self.assertEqual(string.lstrip(), "Hello, World!  ")
        self.assertEqual(string.rstrip(), "  Hello, World!")

if __name__ == '__main__':
    unittest.main()

