#!/usr/bin/env python3
"""Helper for building the macOS bundle with PyInstaller."""

import os
from pathlib import Path

import PyInstaller.__main__

ARGS = [
    "app/__init__.py",
    "--name=Glimpser",
    "--onefile",
    "--windowed",
    "--add-data=app/templates:templates",
    "--add-data=app/static:static",
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
    "--icon=app/static/favicon.ico",
]


def build() -> None:
    """Invoke PyInstaller with macOS settings."""
    os.chdir(Path(__file__).resolve().parent)
    PyInstaller.__main__.run(ARGS)


def main() -> None:
    """Command-line entry point."""
    build()


if __name__ == "__main__":
    main()
