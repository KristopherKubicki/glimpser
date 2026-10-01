#!/usr/bin/env python3
"""Ensure all documentation files are referenced in mkdocs navigation."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

MKDOCS_FILE = Path("mkdocs.yml")
DOCS_DIR = Path("docs")
EXCLUDE_FILE = DOCS_DIR / "exclude_docs"


def _flatten_nav(items):
    result: list[str] = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            for value in item.values():
                if isinstance(value, list):
                    result.extend(_flatten_nav(value))
                else:
                    result.append(value)
    return result


def parse_mkdocs_nav(file: Path = MKDOCS_FILE) -> list[str]:
    """Return list of markdown files from mkdocs.yml navigation."""
    if not file.exists():
        raise FileNotFoundError(file)
    data = yaml.safe_load(file.read_text())
    nav = data.get("nav", [])
    return [p for p in _flatten_nav(nav) if p.endswith(".md")]


def list_docs(directory: Path = DOCS_DIR) -> list[str]:
    """Return list of markdown files relative to docs directory."""
    return [p.relative_to(directory).as_posix() for p in directory.rglob("*.md")]


def parse_exclude(file: Path = EXCLUDE_FILE) -> list[str]:
    """Return list of docs excluded from navigation."""
    if not file.exists():
        return []
    return [line.strip() for line in file.read_text().splitlines() if line.strip()]


def main() -> int:
    nav_docs = set(parse_mkdocs_nav())
    all_docs = set(list_docs())
    excluded = set(parse_exclude())
    missing = sorted(all_docs - nav_docs - excluded)
    if missing:
        print("Docs missing from mkdocs nav:", missing, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
