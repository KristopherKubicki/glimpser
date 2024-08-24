# tests/retention_policy.py

import unittest
import tempfile
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.retention_policy import delete_old_files

class TestRetentionPolicy(unittest.TestCase):

    def test_delete_old_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create dummy files with different ages
            for i in range(5):
                file_path = os.path.join(temp_dir, f"file{i}.txt")
                with open(file_path, 'w') as f:
                    f.write("Some content")
                os.utime(file_path, (i * 1000, i * 1000))  # Modify file creation time
            
            # Run the delete function
            files = os.listdir(temp_dir)
            delete_old_files([os.path.join(temp_dir, f) for f in files], max_age=0, max_size=0, minimum=2)
            
            # Check that only two files remain
            remaining_files = os.listdir(temp_dir)
            self.assertEqual(len(remaining_files), 2)

if __name__ == '__main__':
    unittest.main()

