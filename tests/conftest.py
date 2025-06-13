import os

import pytest_socket

# Skip end-to-end tests unless explicitly enabled
os.environ.setdefault("SKIP_E2E", "1")

# Block network access during tests to avoid accidental HTTP requests.
pytest_socket.disable_socket()
