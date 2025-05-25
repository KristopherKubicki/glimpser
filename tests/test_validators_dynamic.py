import unittest
import importlib.util
import os
import sys
import types

class TestValidateTemplateName(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # provide minimal werkzeug.utils.secure_filename
        wu_mod = types.ModuleType('werkzeug.utils')
        wu_mod.secure_filename = lambda x: x
        w_mod = types.ModuleType('werkzeug')
        w_mod.utils = wu_mod
        sys.modules.setdefault('werkzeug', w_mod)
        sys.modules.setdefault('werkzeug.utils', wu_mod)

        module_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'validators.py'))
        spec = importlib.util.spec_from_file_location('validators', module_path)
        cls.validators = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.validators)

    def test_validate_template_name_valid(self):
        func = self.validators.validate_template_name
        self.assertEqual(func('valid-name_123'), 'valid-name_123')

    def test_validate_template_name_invalid(self):
        func = self.validators.validate_template_name
        self.assertIsNone(func('invalid name'))
        self.assertIsNone(func('../escape'))
        self.assertIsNone(func('-start'))
        self.assertIsNone(func('end-'))
        self.assertIsNone(func('a'*33))

if __name__ == '__main__':
    unittest.main()
