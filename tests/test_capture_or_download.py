import unittest
from unittest.mock import patch
from app.utils.screenshots import capture_or_download

class TestCaptureOrDownload(unittest.TestCase):
    @patch('app.utils.screenshots.cas_error')
    @patch('app.utils.screenshots.download_image')
    @patch('app.utils.screenshots.get_content_type')
    @patch('app.utils.screenshots.is_address_reachable')
    def test_capture_success(self, mock_reachable, mock_content, mock_download, mock_cas):
        mock_reachable.return_value = True
        mock_content.return_value = ('image/png', True)
        mock_download.return_value = True
        template = {'url': 'http://example.com/test.png', 'timeout': 1}
        self.assertTrue(capture_or_download('cam', template))
        mock_download.assert_called_once()

    @patch('app.utils.screenshots.cas_error')
    @patch('app.utils.screenshots.download_image')
    @patch('app.utils.screenshots.get_content_type')
    @patch('app.utils.screenshots.is_address_reachable')
    def test_capture_unreachable(self, mock_reachable, mock_content, mock_download, mock_cas):
        mock_reachable.return_value = False
        template = {'url': 'http://badhost/test.png'}
        self.assertFalse(capture_or_download('cam', template))
        mock_download.assert_not_called()

if __name__ == '__main__':
    unittest.main()
