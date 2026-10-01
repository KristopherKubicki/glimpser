"""The web application must start without the optional curses dashboard."""

import os
import subprocess
import sys


def test_application_import_without_curses():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.modules['curses'] = None; "
            "import app; from app.utils import file_locks; "
            "assert 'app.utils.console_dashboard' not in sys.modules",
        ],
        env={**os.environ, "GLIMPSER_SKIP_DB_INIT": "1"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
