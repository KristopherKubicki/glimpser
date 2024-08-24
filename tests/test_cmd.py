#!env/bin/python3

import unittest
import json
import subprocess
import sys
import os
from datetime import datetime
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

class TestTimestampHandling(unittest.TestCase):

    def test_get_latest_date_with_files(self):
        with patch('os.path.exists', return_value=True):
            with patch('os.path.getmtime', return_value=1609459200):  # Mocked timestamp for 2021-01-01 00:00:00 # UTC?
                date = get_latest_date('/some/directory')
                self.assertEqual(date, '2021-01-01 00:00:00')

    def test_get_latest_date_no_files(self):
        with patch('os.path.exists', return_value=False):
            date = get_latest_date('/some/directory')
            self.assertIsNone(date)

    def test_get_latest_date_with_empty_dir(self):
        with patch('os.listdir', return_value=[]):
            date = get_latest_date('/some/directory')
            self.assertIsNone(date)

class TestSortedFileRetrieval(unittest.TestCase):

    '''
    @patch('os.listdir')
    @patch('os.path.getctime')
    def test_get_files_sorted_by_creation_time(self, mock_getctime, mock_listdir):
        mock_listdir.return_value = ['file1.txt', 'file2.txt', 'file3.txt']
        mock_getctime.side_effect = [3, 1, 2]  # file2 should come first, then file3, then file1

        files = get_files_sorted_by_creation_time('/some/directory')
        expected_order = ['/some/directory/file2.txt', '/some/directory/file3.txt', '/some/directory/file1.txt']
        self.assertEqual(files, expected_order)
    '''
    pass

if __name__ == '__main__':
    unittest.main()

