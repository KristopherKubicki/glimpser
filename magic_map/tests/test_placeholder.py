"""Simple placeholder test for Magic Map Utility."""

import os
import sys

# Ensure repository root is on the import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from magic_map import main


def test_main(capsys):
    """Verify placeholder entry point prints output."""
    main.main()
    captured = capsys.readouterr()
    assert "Magic Map Utility" in captured.out
