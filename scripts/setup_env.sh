#!/bin/bash
# Set up local development environment
set -e

pip install -e .[dev]  # add '[agents]' for offline agent toolkit
npm install
pre-commit install
