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
    os.makedirs(os.path.dirname(DATABASE_PATH))

# initial setup.  If there is no database, then the application is starting from scratch
if not os.path.exists(DATABASE_PATH):  # check some other things too..
    from generate_credentials import generate_credentials

    generate_credentials()


if __name__ == "__main__":

    from app.config import HOST, LOGGING_PATH, PORT

    if not os.path.isdir(os.path.dirname(LOGGING_PATH)):
        os.makedirs(os.path.dirname(LOGGING_PATH))

    logging.basicConfig(
        filename=LOGGING_PATH,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    from app import create_app

    app = create_app()

    app.run(host=HOST, port=PORT)

