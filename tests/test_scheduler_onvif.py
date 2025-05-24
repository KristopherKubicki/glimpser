import unittest
import os
import sys
from unittest.mock import patch, MagicMock
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils import scheduling


class TestSchedulerONVIF(unittest.TestCase):
    @patch('app.utils.scheduling.send_motion_event')
    def test_motion_event_called(self, mock_event):
        template = {'name': 'cam1', 'motion': 0, 'groups': ''}
        os.makedirs('data/screenshots/cam1', exist_ok=True)
        Image.new('RGB', (1, 1)).save('data/screenshots/cam1/1.png')
        Image.new('RGB', (1, 1)).save('data/screenshots/cam1/2.png')

        with patch('app.utils.scheduling.get_template', return_value=template), \
             patch('app.utils.scheduling.save_template'), \
             patch('app.utils.scheduling.capture_or_download', return_value=True), \
             patch('app.utils.scheduling.calculate_difference_fast', return_value=1), \
             patch('app.utils.scheduling.is_mostly_blank', return_value=False), \
             patch('os.symlink'), patch('os.rename'), patch('os.unlink'):
            scheduling.update_camera('cam1', template)
        self.assertTrue(mock_event.called)


if __name__ == '__main__':
    unittest.main()
