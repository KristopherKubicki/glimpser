#!/usr/bin/env bash
###############################################################################
# bootstrap-python.sh – timeout & size-aware (v6-f, faster + shellcheck)
###############################################################################
set -Eeuo pipefail
[[ ${DEBUG:-0} == 1 ]] && set -x

# ─── System packages ──────────────────────────────────────────────────────────
# shellcheck is only distributed as an OS package; grab it first so the cache
# refresh overlaps later network fetches.
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends shellcheck

# ─── 1 · Runtime / production ────────────────────────────────────────────────
uv pip install --system alembic==1.16.1 apscheduler==3.11.0 \
  fake-useragent==2.2.0 flask==3.1.1 flask-apscheduler==1.13.1 \
  flask-login==0.6.3 jinja2==3.1.6 "numpy>=1.26,<2.0" pdf2image==1.17.0 \
  pillow==11.2.1 "psutil~=7.0.0" pynput==1.8.1 \
  "python-dateutil>=2.9.0.post0" "python-dotenv>=1.1.0" \
  pyvirtualdisplay==3.0 pywebpush==2.0.3 selenium==4.33.0 \
  sqlalchemy==2.0.41 undetected-chromedriver==3.5.5 \
  webdriver-manager==4.0.2 werkzeug==3.1.3 yt-dlp==2025.5.22 \
  "onnxruntime-gpu~=1.18; sys_platform!='darwin'" \
  "onnxruntime~=1.18; sys_platform=='darwin'" setproctitle==1.3.3 \
  "filelock>=3.12" "PyYAML>=6.0" "uv>=0.6"

# ─── 2 · Dev toolchain (pytest-xdist added) ──────────────────────────────────
uv pip install --system "black>=25.1" coverage>=7.9 flake8>=7.2 isort>=6.0 \
  mkdocs>=1.6 mypy>=1.16 pre-commit>=4.2 "pytest>=8.3,<8.5" \
  pytest-xdist>=3.6 "uv>=0.6" pyinstaller>=6.14.1 pylint>=3.3.7 prettier \
  pytest-socket ruff>=0.4.4 pytest-cov>=6.1 hypothesis>=6.135 \
  nox>=2025.2 bandit>=1.7 py-spy>=0.4 commitizen>=3.12

# ─── 3 · Ancillary “agents” ──────────────────────────────────────────────────
uv pip install --system pytest-benchmark interrogate yamllint \
  pre-commit-docker gitlint vulture pytest-xdist  # keeps parity with block 2

# ─── 4 · Node toolchain (quiet + no audit/fund chatter) ──────────────────────
npm install --silent --no-progress --no-audit --no-fund \
  --save-dev jest stylelint eslint
