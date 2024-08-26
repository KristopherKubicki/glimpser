import PyInstaller.__main__
import os

# Ensure we're in the correct directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

PyInstaller.__main__.run(
    [
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
)
