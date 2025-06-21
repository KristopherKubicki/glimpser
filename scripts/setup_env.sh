#!/bin/bash
# Set up local development environment
set -e

pip install .[dev]
npm install
pre-commit install
