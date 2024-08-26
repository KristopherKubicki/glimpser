#!/bin/bash

# Exit on error
set -e

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
mkdir -p debian/glimpser/opt/glimpser
cp -R app debian/glimpser/opt/glimpser/
cp requirements.txt debian/glimpser/opt/glimpser/
cp -R data debian/glimpser/opt/glimpser/
mkdir -p debian/glimpser/etc/systemd/system
cat > debian/glimpser/etc/systemd/system/glimpser.service << EOL
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

dpkg-deb --build debian/glimpser

echo "Debian package built successfully."

# Build Windows executable
echo "Building Windows executable..."
python3 -m pip install pyinstaller
python3 build_windows.py

echo "Windows executable built successfully."

echo "Build process completed. You can find the packages in the current directory."