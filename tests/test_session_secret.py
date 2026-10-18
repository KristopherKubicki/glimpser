from concurrent.futures import ThreadPoolExecutor

import pytest

from app.session_secret import resolve_session_secret


def test_unconfigured_secret_persists_and_is_private(tmp_path):
    database = str(tmp_path / "install.db")
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(
            pool.map(lambda _: resolve_session_secret("", database), range(8))
        )
    assert len(set(values)) == 1
    assert len(values[0]) == 64
    assert resolve_session_secret("default_secret_key", database) == values[0]
    assert (tmp_path / "install.session-secret").stat().st_mode & 0o777 == 0o600
    assert resolve_session_secret("", str(tmp_path / "other.db")) != values[0]


def test_configured_key_is_preserved_without_writing(tmp_path):
    assert (
        resolve_session_secret("explicit-test-key", str(tmp_path / "db"))
        == "explicit-test-key"
    )
    assert list(tmp_path.iterdir()) == []


def test_build_mode_uses_ephemeral_key_without_writing(tmp_path):
    key = resolve_session_secret(None, str(tmp_path / "db"), persist=False)
    assert len(key) == 64
    assert list(tmp_path.iterdir()) == []


def test_corrupt_persisted_key_fails_closed(tmp_path):
    (tmp_path / "db.session-secret").write_text("broken")
    with pytest.raises(ValueError, match="Invalid persisted"):
        resolve_session_secret("", str(tmp_path / "db"))
