"""Utility to condense repeated log messages."""

import sys
from collections import Counter
from typing import Iterable


def _read_lines(file: Iterable[str]) -> list[str]:
    return [line.strip() for line in file if line.strip()]


def clean_lines(lines: Iterable[str]) -> list[str]:
    counts = Counter(lines)
    cleaned: list[str] = []
    for line, count in counts.most_common():
        prefix = f"[{count}] " if count > 1 else ""
        cleaned.append(f"{prefix}{line}")
    return cleaned


def main() -> None:
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            lines = _read_lines(f)
    else:
        lines = _read_lines(sys.stdin)

    for out_line in clean_lines(lines):
        print(out_line)


if __name__ == "__main__":
    main()
