#!/bin/bash
# Set up local development environment
set -e

pip install .
if [ -f requirements-dev.txt ]; then
    pip install -r requirements-dev.txt
fi
npm install
pre-commit install
