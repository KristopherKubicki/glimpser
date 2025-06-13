#!/usr/bin/env python3
"""Validate mkdocs.yml exclude_docs matches docs/exclude_docs list."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

MKDOCS_FILE = Path("mkdocs.yml")
DOCS_LIST_FILE = Path("docs/exclude_docs")


def parse_mkdocs_excludes(file: Path = MKDOCS_FILE) -> list[str]:
    """Return list of excluded docs from mkdocs.yml."""
    if not file.exists():
        raise FileNotFoundError(file)
    data = yaml.safe_load(file.read_text())
    value = data.get("exclude_docs", "")
    return [line.strip() for line in value.splitlines() if line.strip()]


def parse_docs_list(file: Path = DOCS_LIST_FILE) -> list[str]:
    """Return expected list of excluded docs."""
    if not file.exists():
        raise FileNotFoundError(file)
    return [line.strip() for line in file.read_text().splitlines() if line.strip()]


def main() -> int:
    mkdocs_list = parse_mkdocs_excludes()
    expected_list = parse_docs_list()
    if mkdocs_list != expected_list:
        print("exclude_docs mismatch", file=sys.stderr)
        print(f"mkdocs.yml: {mkdocs_list}", file=sys.stderr)
        print(f"docs/exclude_docs: {expected_list}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
