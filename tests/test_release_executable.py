"""Native release checks must read TOML independently of the platform locale."""

import runpy
import subprocess
import sys
from pathlib import Path


def test_release_check_reads_utf8_metadata(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/check_release_executable.py"
    (tmp_path / "pyproject.toml").write_bytes(
        '[project]\nversion = "0.2.10"\ndescription = "“camera”"\n'.encode("utf-8")
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [str(script), "Glimpser.exe"])
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, stdout="Glimpser 0.2.10\n", stderr=""
        ),
    )

    # A text-mode read would use the Windows runner's legacy locale.
    def reject_text_read(*args, **kwargs):
        raise AssertionError("TOML must be read as binary UTF-8")

    monkeypatch.setattr(Path, "read_text", reject_text_read)
    runpy.run_path(str(script), run_name="__main__")
