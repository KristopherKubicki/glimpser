import unittest
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestEmptyDataStructures(unittest.TestCase):

    def test_empty_list(self):
        empty_list = []
        self.assertEqual(len(empty_list), 0)
        self.assertEqual(empty_list, [])

    def test_empty_dict(self):
        empty_dict = {}
        self.assertEqual(len(empty_dict), 0)
        self.assertEqual(empty_dict, {})

    def test_empty_string(self):
        empty_string = ""
        self.assertEqual(len(empty_string), 0)
        self.assertEqual(empty_string, "")

class TestSetOperations(unittest.TestCase):

    def test_set_union(self):
        set_a = {1, 2, 3}
        set_b = {3, 4, 5}
        result = set_a.union(set_b)
        self.assertEqual(result, {1, 2, 3, 4, 5})

    def test_set_intersection(self):
        set_a = {1, 2, 3}
        set_b = {3, 4, 5}
        result = set_a.intersection(set_b)
        self.assertEqual(result, {3})

    def test_set_difference(self):
        set_a = {1, 2, 3}
        set_b = {3, 4, 5}
        result = set_a.difference(set_b)
        self.assertEqual(result, {1, 2})

class TestTupleOperations(unittest.TestCase):

    def test_tuple_slicing(self):
        tup = (1, 2, 3, 4)
        self.assertEqual(tup[:2], (1, 2))

    def test_tuple_concatenation(self):
        tup1 = (1, 2)
        tup2 = (3, 4)
        self.assertEqual(tup1 + tup2, (1, 2, 3, 4))

class TestFileExistence(unittest.TestCase):

    def test_file_existence(self):
        self.assertFalse(os.path.exists("non_existent_file.txt"))
        with tempfile.NamedTemporaryFile(delete=True) as temp_file:
            self.assertTrue(os.path.exists(temp_file.name))

class TestBooleanLogic(unittest.TestCase):

    def test_and_logic(self):
        self.assertTrue(True and True)
        self.assertFalse(True and False)

    def test_or_logic(self):
        self.assertTrue(True or False)
        self.assertFalse(False or False)

    def test_not_logic(self):
        self.assertTrue(not False)
        self.assertFalse(not True)

class TestTypeChecking(unittest.TestCase):

    def test_type_error(self):
        with self.assertRaises(TypeError):
            "string" + 5  # Adding a string and an int should raise a TypeError

class TestRangeHandling(unittest.TestCase):

    def test_empty_range(self):
        empty_range = list(range(0))
        self.assertEqual(empty_range, [])

    def test_non_empty_range(self):
        non_empty_range = list(range(5))
        self.assertEqual(non_empty_range, [0, 1, 2, 3, 4])

class TestStringFormatting(unittest.TestCase):

    def test_string_formatting(self):
        formatted_string = "Hello, {}!".format("World")
        self.assertEqual(formatted_string, "Hello, World!")

    def test_f_string(self):
        name = "World"
        formatted_string = f"Hello, {name}!"
        self.assertEqual(formatted_string, "Hello, World!")

class TestDictionaryComprehension(unittest.TestCase):

    def test_simple_dict_comprehension(self):
        numbers = [1, 2, 3, 4, 5]
        squared_dict = {n: n**2 for n in numbers}
        self.assertEqual(squared_dict, {1: 1, 2: 4, 3: 9, 4: 16, 5: 25})

    def test_dict_comprehension_with_condition(self):
        numbers = [1, 2, 3, 4, 5, 6]
        even_squared_dict = {n: n**2 for n in numbers if n % 2 == 0}
        self.assertEqual(even_squared_dict, {2: 4, 4: 16, 6: 36})

    def test_dict_comprehension_with_complex_expression(self):
        words = ['apple', 'banana', 'cherry']
        word_length_dict = {word: len(word) for word in words}
        self.assertEqual(word_length_dict, {'apple': 5, 'banana': 6, 'cherry': 6})

class TestListComprehension(unittest.TestCase):

    def test_simple_list_comprehension(self):
        numbers = [1, 2, 3, 4, 5]
        squared_numbers = [n**2 for n in numbers]
        self.assertEqual(squared_numbers, [1, 4, 9, 16, 25])

    def test_list_comprehension_with_condition(self):
        numbers = [1, 2, 3, 4, 5, 6]
        even_numbers = [n for n in numbers if n % 2 == 0]
        self.assertEqual(even_numbers, [2, 4, 6])

    def test_nested_list_comprehension(self):
        matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        flattened = [num for row in matrix for num in row]
        self.assertEqual(flattened, [1, 2, 3, 4, 5, 6, 7, 8, 9])

if __name__ == '__main__':
    unittest.main()

