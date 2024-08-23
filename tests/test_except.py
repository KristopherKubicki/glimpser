import unittest
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestExceptionHandling(unittest.TestCase):

    def test_zero_division(self):
        with self.assertRaises(ZeroDivisionError):
            result = 1 / 0

    def test_key_error(self):
        test_dict = {"key1": "value1"}
        with self.assertRaises(KeyError):
            value = test_dict["non_existent_key"]

    def test_index_error(self):
        test_list = [1, 2, 3]
        with self.assertRaises(IndexError):
            value = test_list[10]

class TestListOperations(unittest.TestCase):

    def test_list_append(self):
        test_list = [1, 2, 3]
        test_list.append(4)
        self.assertEqual(test_list, [1, 2, 3, 4])

    def test_list_remove(self):
        test_list = [1, 2, 3, 4]
        test_list.remove(3)
        self.assertEqual(test_list, [1, 2, 4])

    def test_list_sort(self):
        test_list = [3, 1, 4, 2]
        test_list.sort()
        self.assertEqual(test_list, [1, 2, 3, 4])

class TestDictionaryOperations(unittest.TestCase):

    def test_dict_add_key(self):
        test_dict = {"key1": "value1"}
        test_dict["key2"] = "value2"
        self.assertEqual(test_dict, {"key1": "value1", "key2": "value2"})

    def test_dict_update_value(self):
        test_dict = {"key1": "value1"}
        test_dict["key1"] = "new_value"
        self.assertEqual(test_dict["key1"], "new_value")

    def test_dict_delete_key(self):
        test_dict = {"key1": "value1", "key2": "value2"}
        del test_dict["key1"]
        self.assertNotIn("key1", test_dict)
        self.assertEqual(test_dict, {"key2": "value2"})

if __name__ == '__main__':
    unittest.main()

