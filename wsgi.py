"""Expose the Flask application for WSGI servers."""

from main import create_application

app = create_application()
