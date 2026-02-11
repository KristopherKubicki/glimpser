#!/usr/bin/env bash
###############################################################################
# bootstrap-python.sh — turbo variant, GPU-optional
#   • Default: CPU-only onnxruntime (small wheel)
#   • Enable GPU: GLIMPSER_GPU=1 ./bootstrap-python.sh
###############################################################################
set -Eeuo pipefail
shopt -s lastpipe

export DEBIAN_FRONTEND=noninteractive
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONUNBUFFERED=1
export UV_CACHE_DIR="${HOME}/.cache/uv"
mkdir -p "$UV_CACHE_DIR"

# ─── shellcheck (static binary, no apt slow-down) ────────────────────────────
curl -sSL https://github.com/koalaman/shellcheck/releases/download/v0.9.0/shellcheck-v0.9.0.linux.x86_64.tar.xz \
  | sudo tar -xJ --strip-components=1 -C /usr/local/bin shellcheck-v0.9.0/shellcheck

# ─── Python deps (single uv call) ────────────────────────────────────────────
ORT_PKG="onnxruntime==1.18.0"          # ~70 MB CPU wheel
[[ "${GLIMPSER_GPU:-0}" == "1" ]] && ORT_PKG="onnxruntime-gpu==1.18.0"  # ~600 MB

uv pip install --system -q \
  alembic==1.16.1 apscheduler==3.11.0 fake-useragent==2.2.0 \
  flask==3.1.1 flask-apscheduler==1.13.1 flask-login==0.6.3 \
  jinja2==3.1.6 "numpy>=1.26,<2.0" pdf2image==1.17.0 pillow==11.2.1 \
  "psutil~=7.0.0" pynput==1.8.1 "python-dateutil>=2.9.0.post0" \
  "python-dotenv>=1.1.0" pyvirtualdisplay==3.0 pywebpush==2.0.3 \
  selenium==4.33.0 sqlalchemy==2.0.41 undetected-chromedriver==3.5.5 \
  webdriver-manager==4.0.2 werkzeug==3.1.3 yt-dlp==2025.5.22 \
  setproctitle==1.3.3 "filelock>=3.12" "PyYAML>=6.0" "${ORT_PKG}" \
  coverage>=7.9 mkdocs>=1.6 \
  mypy>=1.16 pre-commit>=4.2 "pytest>=8.3,<8.5" pytest-xdist>=3.6 \
  pyinstaller>=6.14.1 pylint>=3.3.7 prettier pytest-socket ruff>=0.4.4 \
  pytest-cov>=6.1 hypothesis>=6.135 nox>=2025.2 bandit>=1.7 py-spy>=0.4 \
  commitizen>=3.12 pytest-benchmark interrogate yamllint \
  pre-commit-docker gitlint vulture

# ─── Node tooling ───────────────────────────────────────────────────────
# 1. Install project-local devDeps (fast path = npm ci if lockfile exists).
# 2. Top-up global tools *only* for pre-commit hooks that look in $PATH.
#    (Keeps the layer cache small & avoids duplicate installs.)

if [[ -f package.json ]]; then
  npm set progress=false  # prettier CI output
  if [[ -f package-lock.json ]]; then
    npm ci     --silent --no-audit --no-fund --legacy-peer-deps
  else
    npm install --silent --no-audit --no-fund --legacy-peer-deps
  fi
else
  echo "⚠️  No package.json found – skipping Node dependency install"
fi

# Pre-commit’s lint-css hook expects stylelint & config on $PATH.
# Install exactly what the hook needs, nothing more.
npm install -g --silent --no-progress --no-audit --no-fund \
  stylelint@$(npm view stylelint dist-tags.latest) \
  stylelint-config-standard@$(npm view stylelint-config-standard dist-tags.latest) \
  eslint@$(npm view eslint dist-tags.latest)
