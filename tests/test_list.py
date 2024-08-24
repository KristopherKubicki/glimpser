import unittest

class TestListOperations(unittest.TestCase):

    def test_list_sorting(self):
        data = [3, 1, 4, 1, 5, 9, 2]
        data.sort()
        self.assertEqual(data, [1, 1, 2, 3, 4, 5, 9])

    def test_list_appending(self):
        data = []
        data.append(42)
        self.assertEqual(data, [42])

    def test_list_filtering(self):
        data = [1, 2, 3, 4, 5]
        filtered_data = list(filter(lambda x: x % 2 == 0, data))
        self.assertEqual(filtered_data, [2, 4])

