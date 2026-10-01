#!/usr/bin/env python3
"""Helper for building the macOS bundle with PyInstaller."""

import os
from pathlib import Path

import PyInstaller.__main__

ARGS = [
    "main.py",
    "--name=Glimpser",
    "--onefile",
    "--console",
    "--add-data=app/templates:app/templates",
    "--add-data=app/static:app/static",
    "--hidden-import=flask",
    "--hidden-import=flask_apscheduler",
    "--hidden-import=sqlalchemy",
    "--hidden-import=werkzeug",
    "--hidden-import=jinja2",
    "--hidden-import=PIL",
    "--hidden-import=numpy",
    "--hidden-import=selenium",
    "--hidden-import=undetected_chromedriver",
    "--hidden-import=yt_dlp",
    "--hidden-import=pdf2image",
    "--hidden-import=pyvirtualdisplay",
    "--exclude-module=onnxruntime",  # Skip optional onnxruntime to speed up build
    "--icon=app/static/favicon.ico",
]


def build() -> None:
    """Invoke PyInstaller with macOS settings."""
    previous = os.environ.get("GLIMPSER_SKIP_DB_INIT")
    os.environ["GLIMPSER_SKIP_DB_INIT"] = "1"
    os.chdir(Path(__file__).resolve().parent)
    try:
        PyInstaller.__main__.run(ARGS)
    finally:
        if previous is None:
            os.environ.pop("GLIMPSER_SKIP_DB_INIT", None)
        else:
            os.environ["GLIMPSER_SKIP_DB_INIT"] = previous


def main() -> None:
    """Command-line entry point."""
    build()


if __name__ == "__main__":
    main()
