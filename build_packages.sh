#!/bin/bash

# Exit on error and undefined variables, fail on pipeline errors
set -euo pipefail

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check for required tools
if ! command_exists dpkg-deb; then
    echo "dpkg-deb is not installed. Please install it to build Debian packages."
    exit 1
fi

if ! command_exists python3; then
    echo "python3 is not installed. Python 3.11 or newer is required to build the Debian package."
    exit 1
fi

# Build Debian package
echo "Building Debian package..."
# Read version from pyproject so the package version matches the Python
# distribution. tomllib is available from Python 3.11.
VERSION=$(python3 - <<'EOF'
import tomllib, pathlib
data = tomllib.loads(pathlib.Path("pyproject.toml").read_text())
print(data["project"]["version"])
EOF
)
mkdir -p debian
package_stage=$(mktemp -d debian/glimpser-stage.XXXXXX)
trap 'rm -rf -- "$package_stage"' EXIT
python3 scripts/stage_debian.py . "$package_stage/opt/glimpser"
mkdir -p "$package_stage/lib/systemd/system"
cp debian/glimpser.service "$package_stage/lib/systemd/system/glimpser.service"

# Copy packaging metadata
mkdir -p "$package_stage/DEBIAN" || { echo "Failed to create DEBIAN directory"; exit 1; }
cat > "$package_stage/DEBIAN"/control <<EOF
Package: glimpser
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: Kristopher Kubicki <kristopher@glimpser.net>
Depends: python3 (>= 3.11), python3-venv, adduser, init-system-helpers, ffmpeg, xvfb, poppler-utils
Recommends: chromium, chromium-driver
Description: Glimpser - A web monitoring and screenshot tool
 Glimpser is a powerful tool for monitoring websites and capturing
 screenshots. It provides features for scheduling, archiving, and
 analyzing web content.
EOF
for maintainer_script in postinst prerm postrm; do
    cp "debian/$maintainer_script" "$package_stage/DEBIAN/$maintainer_script"
    chmod 755 "$package_stage/DEBIAN/$maintainer_script"
done

dpkg-deb --build --root-owner-group "$package_stage" debian/glimpser.deb

echo "Debian package built successfully."

# Native Windows and macOS artifacts are built by their dedicated CI jobs.
