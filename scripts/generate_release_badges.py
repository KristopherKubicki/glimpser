from pathlib import Path
import os

BADGES = [
    "[![Python application](https://github.com/KristopherKubicki/glimpser/actions/workflows/python-app.yml/badge.svg)](https://github.com/KristopherKubicki/glimpser/actions/workflows/python-app.yml)",
    "[![Pylint](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml/badge.svg)](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml)",
    "[![Tests](https://github.com/KristopherKubicki/glimpser/actions/workflows/python-app.yml/badge.svg)](https://github.com/KristopherKubicki/glimpser/actions/workflows/python-app.yml)",
    "[![Coverage](https://codecov.io/gh/KristopherKubicki/glimpser/branch/main/graph/badge.svg)](https://codecov.io/gh/KristopherKubicki/glimpser)",
    "[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/kristopherkubicki/glimpser/badge)](https://securityscorecards.dev/viewer/?uri=github.com/kristopherkubicki/glimpser)",
    "[![CodeQL](https://github.com/KristopherKubicki/glimpser/actions/workflows/codeql.yml/badge.svg)](https://github.com/KristopherKubicki/glimpser/actions/workflows/codeql.yml)",
    "[![Docs Build](https://github.com/KristopherKubicki/glimpser/actions/workflows/docs-build.yml/badge.svg)](https://github.com/KristopherKubicki/glimpser/actions/workflows/docs-build.yml)",
]


def main() -> None:
    version = os.environ.get("GITHUB_REF_NAME", "")
    lines = [f"# Release {version}", ""] + BADGES
    Path("release-badges.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
