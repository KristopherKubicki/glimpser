# Glimpser Installation Guide

This guide provides detailed instructions for installing and setting up Glimpser on your system.

## System Requirements

- **Architecture**: Glimpser is primarily designed for x86 architecture.
  - ARM support may require additional work and is not guaranteed.
- **Operating System**: Linux (Ubuntu 20.04 LTS or later recommended)
- **Python**: Version 3.10 to 3.13

## Installation Steps

### 1. Clone the Repository

```sh
git clone https://github.com/KristopherKubicki/glimpser.git
cd glimpser
```

### 2. Install System Dependencies

Before installing Glimpser, you need to install some system dependencies:

```sh
sudo apt-get update
sudo apt-get install -y curl wget gnupg2 software-properties-common apt-transport-https ca-certificates
```

### 3. Install Google Chrome

Google Chrome is required for some of Glimpser's functionality. To install it:

```sh
wget -qO- https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-linux-signing-keyring.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux-signing-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt-get update
sudo apt-get install -y google-chrome-stable
```

### 4. Install FFmpeg

FFmpeg is used for video processing in Glimpser:

```sh
sudo apt-get install -y ffmpeg
```

For hardware-accelerated playback and encoding you may optionally build a custom
version with GPU support. Automatic builds are disabled by default. Set the
environment variable `GLIMPSER_AUTO_BUILD_FFMPEG=1` or run the script manually:

```sh
./scripts/build_gpu_ffmpeg.sh
```

This requires development tools and matching NVIDIA or VA-API drivers
installed on your system.

### 5. Install Python Dependencies

Install the required Python packages:

```sh
pip install .
```

All runtime dependencies, including `psutil`, are defined in `pyproject.toml`.

### 6. (Optional) Configure Environment Variables

Copy `.env.example` to `.env` and adjust values to override defaults:

```sh
cp .env.example .env
# edit .env as needed
```

### 7. Set Up the Database

Initialize the local SQLite database:

```sh
python3 main.py
```

You will be prompted to create a secret key. Follow the guided setup to complete the database initialization.

### 8. Run the Application

After completing the setup, you can run the application:

```sh
python3 main.py
```

Navigate to http://127.0.0.1:8082 in your web browser to access the Glimpser interface and complete the rest of the setup.

## Docker Installation (Alternative)

If you prefer to use Docker, you can use the provided Dockerfile and docker-compose.yaml:

1. Make sure you have Docker and Docker Compose installed.
2. Build and run the Docker container:

```sh
docker-compose up --build
```

This will set up the entire environment, including all necessary dependencies.

## Troubleshooting

- If you encounter issues related to ARM architecture, please note that full ARM support is not currently available. You may need to use an x86 emulator or consider using a different machine.
- For any other issues, please check the project's issue tracker on GitHub or reach out to the maintainers for support.

## Next Steps

After installation, refer to the [Recommendations](recommendations.md) document for ideas on how to effectively use Glimpser for various monitoring and data aggregation tasks.
