import re
import tomllib
from pathlib import Path

PYPROJECT = Path("pyproject.toml")
CITATION = Path("CITATION.cff")
CONFIG = Path("app/config.py")


def get_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text())
    return data["project"]["version"]


def update_citation(version: str) -> None:
    text = CITATION.read_text()
    new_text = re.sub(
        r'^version: "[^"]+"', f'version: "{version}"', text, flags=re.MULTILINE
    )
    if text != new_text:
        CITATION.write_text(new_text)


def update_config(version: str) -> None:
    text = CONFIG.read_text()
    new_text = re.sub(r'_PKG_VERSION = "[^"]+"', f'_PKG_VERSION = "{version}"', text)
    if text != new_text:
        CONFIG.write_text(new_text)


def main() -> None:
    version = get_version()
    update_citation(version)
    update_config(version)


if __name__ == "__main__":
    main()
