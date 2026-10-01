import pytest

from scripts.stage_debian import ROOT_FILES, stage_application


def make_source(root):
    root.mkdir()
    for name in ROOT_FILES:
        (root / name).write_text("source placeholder")
    (root / "app" / "templates").mkdir(parents=True)
    (root / "app" / "templates" / "index.html").write_text("public asset")
    (root / "app" / "__init__.py").write_text("# public code")
    return root


def test_package_excludes_local_state_and_secrets(tmp_path):
    root = make_source(tmp_path / "source")
    for name in (
        "data/glimpser.db",
        "data/config_backup.json",
        "data/db.session-secret",
        ".env",
        "logs/run.log",
        "app/local.db",
        "app/__pycache__/old.pyc",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("PRIVATE-SENTINEL")
    target = tmp_path / "package"
    stage_application(root, target)
    assert (target / "app/templates/index.html").read_text() == "public asset"
    assert not (target / "data").exists()
    assert all(
        b"PRIVATE-SENTINEL" not in p.read_bytes()
        for p in target.rglob("*")
        if p.is_file()
    )


def test_package_rejects_symlink_to_private_data(tmp_path):
    root = make_source(tmp_path / "source")
    private = tmp_path / "private.txt"
    private.write_text("PRIVATE-SENTINEL")
    (root / "app" / "leak.txt").symlink_to(private)
    with pytest.raises(ValueError, match="symlink"):
        stage_application(root, tmp_path / "package")


def test_package_requires_empty_staging_directory(tmp_path):
    root = make_source(tmp_path / "source")
    target = tmp_path / "old-package"
    target.mkdir()
    (target / "old-secret.db").write_text("PRIVATE-SENTINEL")
    with pytest.raises(FileExistsError):
        stage_application(root, target)


def test_debhelper_path_uses_clean_staging(tmp_path):
    import shutil
    import subprocess
    from pathlib import Path

    root = make_source(tmp_path / "source")
    (root / "scripts").mkdir()
    shutil.copyfile("scripts/stage_debian.py", root / "scripts/stage_debian.py")
    (root / "data").mkdir()
    (root / "data/private.json").write_text("PRIVATE-SENTINEL")
    subprocess.run(
        ["make", "-f", str(Path("debian/rules").resolve()), "override_dh_auto_install"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    staged = root / "debian/glimpser/opt/glimpser"
    assert (staged / "app/templates/index.html").exists()
    assert not (staged / "data").exists()
