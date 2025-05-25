# tests/retention_policy.py

import unittest
import tempfile
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.retention_policy import delete_old_files

class TestRetentionPolicy(unittest.TestCase):

    def test_delete_old_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create dummy files in sequence so creation times increase
            file_paths = []
            for i in range(5):
                file_path = os.path.join(temp_dir, f"file{i}.txt")
                with open(file_path, 'w') as f:
                    f.write("Some content")
                file_paths.append(file_path)
                time.sleep(0.01)  # ensure distinct timestamps
            
            # Run the delete function
            delete_old_files(file_paths, max_age=0, max_size=0, minimum=2)

            # Check that only the two newest files remain
            remaining_files = os.listdir(temp_dir)
            self.assertEqual(set(remaining_files), {"file3.txt", "file4.txt"})

if __name__ == '__main__':
    unittest.main()

