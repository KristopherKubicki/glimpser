import os

# Skip end-to-end tests unless explicitly enabled
os.environ.setdefault("SKIP_E2E", "1")
