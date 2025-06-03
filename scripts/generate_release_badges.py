from pathlib import Path
import os

BADGES = [
    "[![Python application](https://github.com/KristopherKubicki/glimpser/actions/workflows/python-app.yml/badge.svg)](https://github.com/KristopherKubicki/glimpser/actions/workflows/python-app.yml)",
    "[![Tests](https://github.com/KristopherKubicki/glimpser/actions/workflows/python-app.yml/badge.svg)](https://github.com/KristopherKubicki/glimpser/actions/workflows/python-app.yml)",
    "[![Pylint 3.8](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml/badge.svg?label=pylint%203.8)](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml)",
    "[![Pylint 3.9](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml/badge.svg?label=pylint%203.9)](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml)",
    "[![Pylint 3.10](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml/badge.svg?label=pylint%203.10)](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml)",
    "[![Pylint 3.11](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml/badge.svg?label=pylint%203.11)](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml)",
    "[![Pylint 3.12](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml/badge.svg?label=pylint%203.12)](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml)",
    "[![GitHub release](https://img.shields.io/github/v/release/KristopherKubicki/glimpser)](https://github.com/KristopherKubicki/glimpser/releases/latest)",
    "[![PyPI version](https://img.shields.io/pypi/v/glimpser)](https://pypi.org/project/glimpser/)",
    "[![Coverage](https://codecov.io/gh/KristopherKubicki/glimpser/branch/main/graph/badge.svg)](https://codecov.io/gh/KristopherKubicki/glimpser)",
    "[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/KristopherKubicki/glimpser/badge)](https://securityscorecards.dev/viewer/?uri=github.com/KristopherKubicki/glimpser)",
    "[![CodeQL](https://github.com/KristopherKubicki/glimpser/actions/workflows/codeql.yml/badge.svg)](https://github.com/KristopherKubicki/glimpser/actions/workflows/codeql.yml)",
    "[![Docs Build](https://github.com/KristopherKubicki/glimpser/actions/workflows/docs-build.yml/badge.svg)](https://github.com/KristopherKubicki/glimpser/actions/workflows/docs-build.yml)",
]


def main() -> None:
    version = os.environ.get("GITHUB_REF_NAME", "")
    lines = [f"# Release {version}", ""] + BADGES
    Path("release-badges.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
