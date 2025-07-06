#!/usr/bin/env bash
set -euo pipefail

# Determine repository root directory
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Install base system packages
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev \
    curl ca-certificates build-essential git

# Install Node.js 20 via NodeSource
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs

# Create Python virtual environment
if [ ! -d .venv ]; then
    python3.12 -m venv .venv
fi
source .venv/bin/activate

pip install --upgrade pip
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi
pip install black flake8 pytest pre-commit

# Install Node dependencies if present
if [ -f package.json ]; then
    npm install
fi

# Install git hooks via pre-commit
pre-commit install

echo "Setup complete."
