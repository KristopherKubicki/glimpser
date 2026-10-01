"""Persist a private signing key when an installation has no configured key."""

import os
import secrets
from pathlib import Path

from filelock import FileLock


def resolve_session_secret(
    configured: str | None, database_path: str, *, persist: bool = True
) -> str:
    """Preserve configured secrets; replace missing or known-default values."""
    if configured and configured.strip() and configured != "default_secret_key":
        return configured
    if not persist:
        # Packaging must not write an installation key into its build tree.
        return secrets.token_hex(32)
    path = Path(database_path).resolve().with_suffix(".session-secret")
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock", timeout=10):
        if path.is_symlink():
            raise ValueError("Session secret file must not be a symlink")
        if path.exists():
            value = path.read_text(encoding="ascii").strip()
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(
                    "Invalid persisted session secret; restore it or configure SECRET_KEY"
                )
            path.chmod(0o600)
            return value
        value = secrets.token_hex(32)
        # The lock serializes readers; exclusive creation avoids overwriting a key.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            stream.write(value + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return value
