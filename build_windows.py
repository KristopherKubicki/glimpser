#!/usr/bin/env python3
"""Build the Windows executable using PyInstaller."""

import os
from pathlib import Path

import PyInstaller.__main__

ARGS = [
    "app/__init__.py",  # Entry point of the application
    "--name=Glimpser",  # Name of the executable
    "--onefile",  # Create a one-file bundled executable
    "--windowed",  # Disable console window
    "--add-data=app/templates:templates",  # Include templates directory
    "--add-data=app/static:static",  # Include static directory
    "--hidden-import=flask",  # Include hidden import flask
    "--hidden-import=flask_apscheduler",  # Include hidden import flask_apscheduler
    "--hidden-import=sqlalchemy",  # Include hidden import sqlalchemy
    "--hidden-import=werkzeug",  # Include hidden import werkzeug
    "--hidden-import=jinja2",  # Include hidden import jinja2
    "--hidden-import=PIL",  # Include hidden import PIL
    "--hidden-import=numpy",  # Include hidden import numpy
    "--hidden-import=selenium",  # Include hidden import selenium
    "--hidden-import=undetected_chromedriver",  # Include hidden import undetected_chromedriver
    "--hidden-import=yt_dlp",  # Include hidden import yt_dlp
    "--hidden-import=pdf2image",  # Include hidden import pdf2image
    "--hidden-import=pyvirtualdisplay",  # Include hidden import pyvirtualdisplay
    "--icon=app/static/favicon.ico",  # Path to the icon file
]


def build() -> None:
    """Invoke PyInstaller with Windows settings."""
    os.chdir(Path(__file__).resolve().parent)
    PyInstaller.__main__.run(ARGS)


def main() -> None:
    """Command-line entry point."""
    build()


if __name__ == "__main__":
    main()
