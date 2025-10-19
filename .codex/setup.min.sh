#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: setup.min.sh [OPTIONS]

Provision a lightweight local development environment. The script keeps
side-effects to a minimum so repeated runs are fast.

Options:
  --with-node   Install Node.js dependencies in addition to Python ones.
  -h, --help    Show this help message and exit.
USAGE
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WITH_NODE=0

while (($#)); do
  case "$1" in
    --with-node)
      WITH_NODE=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

PYTHON_BIN=${PYTHON:-python3}
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  printf 'Python 3 is required but not found. Set PYTHON to override.\n' >&2
  exit 1
fi

VENV_DIR=${VENV_DIR:-"${REPO_ROOT}/.venv"}
if [[ ! -d "$VENV_DIR" ]]; then
  printf 'Creating virtual environment at %s\n' "$VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  printf 'Reusing existing virtual environment at %s\n' "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

printf 'Upgrading pip tooling...\n'
python -m pip install --upgrade pip wheel setuptools >/dev/null

if [[ -f "${REPO_ROOT}/requirements.txt" ]]; then
  printf 'Installing Python dependencies from requirements.txt...\n'
  python -m pip install --requirement "${REPO_ROOT}/requirements.txt"
else
  printf 'No requirements.txt found, skipping Python dependency install.\n'
fi

if (( WITH_NODE )); then
  if command -v npm >/dev/null 2>&1 && [[ -f "${REPO_ROOT}/package.json" ]]; then
    printf 'Installing Node.js dependencies (omit dev packages)...\n'
    (cd "$REPO_ROOT" && npm ci --omit=dev --no-audit --prefer-offline)
  else
    printf 'npm or package.json not available; skipping Node.js setup.\n'
  fi
else
  printf 'Skipping Node.js dependencies. Use --with-node to include them.\n'
fi

printf 'Minimal setup complete.\n'
