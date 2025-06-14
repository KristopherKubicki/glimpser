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
    echo "python3 is not installed. Please install it to build the Windows executable."
    exit 1
fi

# Build Debian package
echo "Building Debian package..."
mkdir -p debian/glimpser/opt/glimpser || { echo "Failed to create directory"; exit 1; }
rsync -a app/ debian/glimpser/opt/glimpser/app/ || { echo "Failed to sync app directory"; exit 1; }
cp requirements.txt debian/glimpser/opt/glimpser/ || { echo "Failed to copy requirements.txt"; exit 1; }
rsync -a data/ debian/glimpser/opt/glimpser/data/ || { echo "Failed to sync data directory"; exit 1; }
mkdir -p debian/glimpser/etc/systemd/system || { echo "Failed to create systemd directory"; exit 1; }
cat > debian/glimpser/etc/systemd/system/glimpser.service << EOL || { echo "Failed to create service file"; exit 1; }
[Unit]
Description=Glimpser Web Monitoring Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/glimpser/app/__init__.py
WorkingDirectory=/opt/glimpser
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOL

# Copy packaging metadata
mkdir -p debian/glimpser/DEBIAN || { echo "Failed to create DEBIAN directory"; exit 1; }
cat > debian/glimpser/DEBIAN/control <<EOF
Package: glimpser
Version: 1.0.0
Section: utils
Priority: optional
Architecture: all
Maintainer: Kristopher Kubicki <kristopher@glimpser.net>
Depends: python3, python3-pip
Description: Glimpser - A web monitoring and screenshot tool
 Glimpser is a powerful tool for monitoring websites and capturing
 screenshots. It provides features for scheduling, archiving, and
 analyzing web content.
EOF
if [ -f debian/postinst ]; then
    cp debian/postinst debian/glimpser/DEBIAN/postinst || { echo "Failed to copy postinst"; exit 1; }
    chmod 755 debian/glimpser/DEBIAN/postinst
fi

dpkg-deb --build debian/glimpser

echo "Debian package built successfully."

# Build Windows executable if PyInstaller is available
echo "Building Windows executable..."
if ! python3 -m pip show pyinstaller >/dev/null 2>&1; then
    if ! python3 -m pip install pyinstaller >/dev/null 2>&1; then
        echo "PyInstaller not available; skipping Windows executable build."
        exit 0
    fi
fi

python3 build_windows.py && echo "Windows executable built successfully." || echo "Failed to build Windows executable"

echo "Build process completed. You can find the packages in the current directory."
