#!env/bin/python3
# tests/test_cmd.py

import unittest
import json
import subprocess
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.video_details import get_latest_date
from app.utils.screenshots import parse_url
from app.utils.retention_policy import get_files_sorted_by_creation_time

class TestJSONParsing(unittest.TestCase):

    def test_valid_json_parsing(self):
        valid_json = '{"name": "test", "value": 123}'
        data = json.loads(valid_json)
        self.assertEqual(data['name'], "test")
        self.assertEqual(data['value'], 123)

    def test_invalid_json_parsing(self):
        invalid_json = '{"name": "test", "value": 123'
        with self.assertRaises(json.JSONDecodeError):
            json.loads(invalid_json)

class TestCommandExecution(unittest.TestCase):

    @patch('subprocess.check_output')
    def test_successful_command_execution(self, mock_check_output):
        mock_check_output.return_value = b'command output'
        result = subprocess.check_output(['echo', 'hello'])
        self.assertEqual(result, b'command output')

    @patch('subprocess.check_output')
    def test_failed_command_execution(self, mock_check_output):
        mock_check_output.side_effect = subprocess.CalledProcessError(1, 'echo')
        with self.assertRaises(subprocess.CalledProcessError):
            subprocess.check_output(['echo', 'fail'])

if __name__ == '__main__':
    unittest.main()


