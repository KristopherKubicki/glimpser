#!/bin/bash
# Set up local development environment
set -e

pip install -r requirements.txt
if [ -f requirements-dev.txt ]; then
    pip install -r requirements-dev.txt
fi
# Try installing onnxruntime packages with a fallback
python scripts/install_onnxruntime.py || true
npm install
pre-commit install
