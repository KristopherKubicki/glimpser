#!/usr/bin/env python3
"""Validate mkdocs.yml exclude_docs matches docs/exclude_docs list."""

from __future__ import annotations

import sys
from pathlib import Path

MKDOCS_FILE = Path("mkdocs.yml")
DOCS_LIST_FILE = Path("docs/exclude_docs")


def parse_mkdocs_excludes(file: Path = MKDOCS_FILE) -> list[str]:
    """Return list of excluded docs from mkdocs.yml without PyYAML."""
    if not file.exists():
        raise FileNotFoundError(file)
    lines = file.read_text().splitlines()
    result: list[str] = []
    capture = False
    base_indent = 0
    for line in lines:
        stripped = line.strip()
        if not capture and stripped.startswith("exclude_docs:"):
            capture = True
            base_indent = len(line) - len(line.lstrip()) + 2
            continue
        if capture:
            if stripped and (len(line) - len(line.lstrip())) >= base_indent:
                result.append(stripped)
            elif stripped:
                break
    return result


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
        DOCS_LIST_FILE.write_text("\n".join(mkdocs_list) + "\n")
        print("docs/exclude_docs updated", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
