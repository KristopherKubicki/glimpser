#!env/bin/python3
# main.py

import logging
import os

# make sure we are properly in the application directory, we might be remaking a few config files otherwise
os.chdir(os.path.abspath(os.path.dirname(__file__)))

# Check if database exists, and generate credentials if it doesn't
DATABASE_PATH = os.getenv(
    "GLIMPSER_DATABASE_PATH", "data/glimpser.db"
)  # warning, duplicate default value in app/config.py
if not os.path.isdir(os.path.dirname(DATABASE_PATH)):
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

# initial setup.  If there is no database, then the application is starting from scratch
if not os.path.exists(DATABASE_PATH):  # check some other things too..
    from generate_credentials import generate_credentials
    generate_credentials()

from app.config import HOST, LOGGING_PATH, PORT

if not os.path.isdir(os.path.dirname(LOGGING_PATH)):
    os.makedirs(os.path.dirname(LOGGING_PATH), exist_ok=True)

# Define the logging format
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# Create a logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# File handler to log to a file
file_handler = logging.FileHandler(LOGGING_PATH)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Stream handler to log to the console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


from app import create_app
from flask import jsonify

app = create_app()

# @app.route('/health')
# def health_check():
#     return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
