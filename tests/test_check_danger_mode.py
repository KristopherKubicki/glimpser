import os
import sys
import importlib
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestCheckDangerMode(unittest.TestCase):
    def _run_main(self, port_open: bool, needs_patch: bool):
        with (
            patch(
                "app.utils.screenshots.is_chrome_debug_port_open",
                return_value=port_open,
            ),
            patch(
                "scripts.update_chrome_shortcut.shortcuts_need_patch",
                return_value=needs_patch,
            ),
            patch("builtins.print") as mock_print,
        ):
            module = importlib.import_module("scripts.check_danger_mode")
            importlib.reload(module)
            result = module.main()
        return result, mock_print

    def test_detected_and_patched(self):
        result, mock_print = self._run_main(True, False)
        self.assertEqual(result, 0)
        mock_print.assert_any_call("Danger mode detected.")
        mock_print.assert_any_call("Chrome shortcuts are patched.")

    def test_not_detected_needs_patch(self):
        result, mock_print = self._run_main(False, True)
        self.assertEqual(result, 0)
        mock_print.assert_any_call("Danger mode not detected.")
        mock_print.assert_any_call("Chrome shortcuts need patching.")


if __name__ == "__main__":
    unittest.main()
