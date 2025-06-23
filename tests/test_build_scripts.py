import subprocess
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import build_macos
import build_windows


class TestBuildMacOS(TestCase):
    @patch("build_macos.PyInstaller.__main__.run")
    def test_build_invokes_pyinstaller(self, mock_run):
        build_macos.build()
        mock_run.assert_called_once()
        args = mock_run.call_args.args[0]
        self.assertIn("--name=Glimpser", args)


class TestBuildWindows(TestCase):
    @patch("build_windows.PyInstaller.__main__.run")
    def test_build_invokes_pyinstaller(self, mock_run):
        build_windows.build()
        mock_run.assert_called_once()
        args = mock_run.call_args.args[0]
        self.assertIn("--name=Glimpser", args)
        self.assertIn("--collect-binaries=onnxruntime", args)


def test_build_packages_missing_deps(tmp_path):
    script = Path("build_packages.sh")
    result = subprocess.run(
        ["bash", "-c", f"PATH={tmp_path} ./{script.name}"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "dpkg-deb is not installed" in result.stdout
