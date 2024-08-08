import unittest
from glimpser import app

class FlaskTests(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_home_status_code(self):
        # Sends HTTP GET request to the application
        # on the specified path
        result = self.app.get('/')

        # Assert the status code of the response
        self.assertEqual(result.status_code, 200)

if __name__ == '__main__':
    unittest.main()

