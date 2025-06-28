#!/bin/bash
# Set up local development environment
set -e

if ! command -v uv >/dev/null; then
    echo "uv is required. Install it from https://github.com/astral-sh/uv" >&2
    exit 1
fi

uv sync --group dev
npm install
uv run pre-commit install
