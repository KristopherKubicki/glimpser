import unittest
from unittest.mock import patch
from app.utils.template_manager import get_templates
from app.utils.validators import validate_template_name

class TestGetTemplatesWrapper(unittest.TestCase):
    @patch('app.utils.template_manager.get_latest_video_date')
    @patch('app.utils.template_manager.get_latest_screenshot_date')
    @patch('app.utils.template_manager.TemplateManager.get_templates')
    def test_sanitized_and_metadata(self, mock_get, mock_screenshot, mock_video):
        mock_get.return_value = {
            'valid_name': {'name': 'valid_name'}
        }
        mock_screenshot.return_value = 's_time'
        mock_video.return_value = 'v_time'

        result = get_templates()
        self.assertIn('valid_name', result)
        self.assertEqual(validate_template_name('valid_name'), 'valid_name')
        self.assertEqual(result['valid_name']['last_screenshot_time'], 's_time')
        self.assertEqual(result['valid_name']['last_video_time'], 'v_time')

if __name__ == '__main__':
    unittest.main()
