#!/bin/bash
# Set up local development environment
set -e

pip install -r requirements.txt
if [ -f requirements-dev.txt ]; then
    pip install -r requirements-dev.txt
fi
pip install flake8 pre-commit
npm install
pre-commit install
