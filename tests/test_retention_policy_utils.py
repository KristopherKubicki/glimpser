import unittest
import importlib.util
import os
import sys
import tempfile
import types
from unittest.mock import patch

class TestRetentionPolicyUtils(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # stub app.config required by the module
        sys.modules['app'] = types.ModuleType('app')
        utils_pkg = types.ModuleType('app.utils'); utils_pkg.__path__ = []
        sys.modules['app'].utils = utils_pkg
        sys.modules['app.utils'] = utils_pkg
        cfg = types.ModuleType('app.config')
        cfg.MAX_COMPRESSED_VIDEO_AGE = 1
        cfg.MAX_RAW_DATA_SIZE = 100
        cfg.SCREENSHOT_DIRECTORY = ''
        cfg.VIDEO_DIRECTORY = ''
        sys.modules['app.config'] = cfg

        module_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'retention_policy.py'))
        spec = importlib.util.spec_from_file_location('retention', module_path)
        cls.retention = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.retention)

    def test_get_files_sorted_by_creation_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            f1 = os.path.join(temp_dir, 'a')
            f2 = os.path.join(temp_dir, 'b')
            f3 = os.path.join(temp_dir, 'c')
            for f in (f1, f2, f3):
                open(f, 'w').close()
            ctime_map = {f1:3, f2:1, f3:2}
            with patch('os.path.getctime', side_effect=lambda p: ctime_map[p]):
                files = self.retention.get_files_sorted_by_creation_time(temp_dir)
        expected = [os.path.join(temp_dir,'b'), os.path.join(temp_dir,'c'), os.path.join(temp_dir,'a')]
        self.assertEqual(files, expected)

    def test_delete_old_files(self):
        files = ['f0','f1','f2']
        ctime_map = {'f0':900, 'f1':800, 'f2':700}
        size_map = {'f0':10, 'f1':20, 'f2':30}
        removed = []
        with patch('os.path.getctime', side_effect=lambda p: ctime_map[p]), \
             patch('os.path.getsize', side_effect=lambda p: size_map[p]), \
             patch('os.remove', side_effect=lambda p: removed.append(p)), \
             patch('time.time', return_value=1000):
            self.retention.delete_old_files(files, max_age=0, max_size=0, minimum=0)
        self.assertEqual(set(removed), set(files))

if __name__ == '__main__':
    unittest.main()
