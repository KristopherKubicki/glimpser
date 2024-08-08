#!env/bin/python3
# main.py

import os
import logging

os.chdir(os.path.abspath(os.path.dirname(__file__)))

logging.basicConfig(filename='glimpser.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Check if auth.py exists, and generate credentials if it doesn't
if not os.path.exists('auth.py'):
    from generate_credentials import generate_credentials
    generate_credentials()


if __name__ == '__main__':

    from config import HOST, PORT
    from app import create_app

    app = create_app()

    app.run(host=HOST, port=PORT)

