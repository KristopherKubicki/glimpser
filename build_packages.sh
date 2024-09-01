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
mkdir -p debian/glimpser/opt/glimpser || { echo "Failed to create directory"; exit 1; }
cp -R app debian/glimpser/opt/glimpser/ || { echo "Failed to copy app directory"; exit 1; }
cp requirements.txt debian/glimpser/opt/glimpser/ || { echo "Failed to copy requirements.txt"; exit 1; }
cp -R data debian/glimpser/opt/glimpser/ || { echo "Failed to copy data directory"; exit 1; }
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

dpkg-deb --build debian/glimpser

echo "Debian package built successfully."

# Build Windows executable
echo "Building Windows executable..."
python3 -m pip install pyinstaller || { echo "Failed to install PyInstaller"; exit 1; }
python3 build_windows.py || { echo "Failed to build Windows executable"; exit 1; }

echo "Windows executable built successfully."

echo "Build process completed. You can find the packages in the current directory."