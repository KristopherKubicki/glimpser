import unittest
import importlib.util
import os
import sys
import types
from unittest.mock import patch

class TestVideoArchiverUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # minimal dependency stubs
        sys.modules['app'] = types.ModuleType('app')
        utils_pkg = types.ModuleType('app.utils'); utils_pkg.__path__ = []
        sys.modules['app'].utils = utils_pkg
        sys.modules['app.utils'] = utils_pkg
        cfg = types.ModuleType('app.config')
        cfg.MAX_COMPRESSED_VIDEO_AGE = 1
        cfg.MAX_IN_PROCESS_VIDEO_SIZE = 100
        cfg.NAME = ''
        cfg.SCREENSHOT_DIRECTORY = ''
        cfg.VERSION = ''
        cfg.VIDEO_DIRECTORY = ''
        cfg.FFMPEG_PATH = 'ffmpeg'
        cfg.FFPROBE_PATH = 'ffprobe'
        cfg.FFMPEG_HWACCEL = ''
        sys.modules['app.config'] = cfg
        tm = types.ModuleType('app.utils.template_manager')
        tm.get_templates = lambda: {}
        sys.modules['app.utils.template_manager'] = tm
        # validators dependency
        wu_mod = types.ModuleType('werkzeug.utils'); wu_mod.secure_filename=lambda x:x
        w_mod = types.ModuleType('werkzeug'); w_mod.utils = wu_mod
        sys.modules['werkzeug']=w_mod; sys.modules['werkzeug.utils']=wu_mod
        spec_val = importlib.util.spec_from_file_location('app.utils.validators', os.path.join(os.path.dirname(__file__), '..','app','utils','validators.py'))
        val_mod = importlib.util.module_from_spec(spec_val)
        spec_val.loader.exec_module(val_mod)
        sys.modules['app.utils.validators'] = val_mod
        module_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'video_archiver.py'))
        spec = importlib.util.spec_from_file_location('app.utils.video_archiver', module_path)
        cls.va = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.va)

    def test_trim_group_name(self):
        self.assertEqual(self.va.trim_group_name('Hello World'), 'hello_world')

    def test_handle_concat_error(self):
        with patch('os.path.getsize', return_value=1), patch('os.rename') as rn:
            status = self.va.handle_concat_error(Exception('Invalid data found'), 't.mp4','in.mp4')
            self.assertEqual(status, self.va.ConcatStatus.RECOVERED)
            rn.assert_called_once_with('t.mp4','in.mp4')
        with patch('os.path.getsize', return_value=1), patch('os.rename') as rn:
            status = self.va.handle_concat_error(Exception('Resource busy'), 't.mp4','in.mp4')
            self.assertEqual(status, self.va.ConcatStatus.RETRY)
            rn.assert_not_called()
        with patch('os.path.getsize', return_value=1), patch('os.rename') as rn:
            status = self.va.handle_concat_error(Exception('other'), 't.mp4','in.mp4')
            self.assertEqual(status, self.va.ConcatStatus.FATAL)
            rn.assert_called_once_with('t.mp4','in.mp4')

if __name__ == '__main__':
    unittest.main()
