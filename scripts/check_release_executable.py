"""Verify that a frozen application starts and reports its release version."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

if __name__ == "__main__":
    executable = Path(sys.argv[1]).resolve()
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    result = subprocess.run(
        [str(executable), "--version"],
        env={**os.environ, "GLIMPSER_SKIP_DB_INIT": "1"},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    if version not in result.stdout:
        raise SystemExit("Executable did not report the expected release version")
    print(f"{executable.name}: starts and reports {version}")
