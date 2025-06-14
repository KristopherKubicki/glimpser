#!/usr/bin/env python3
"""Install an appropriate onnxruntime package if available."""
import platform
import subprocess
import sys


def try_install(package: str) -> bool:
    """Attempt to install a package and return True on success."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def main() -> None:
    # On non-mac platforms prefer the GPU build and fall back to CPU.
    packages = ["onnxruntime-gpu~=1.18", "onnxruntime~=1.18"]
    if platform.system() == "Darwin":
        packages = ["onnxruntime~=1.18"]

    for pkg in packages:
        if try_install(pkg):
            print(f"Installed {pkg}")
            return
    print("onnxruntime packages not available; object filtering will be disabled")


if __name__ == "__main__":
    main()
