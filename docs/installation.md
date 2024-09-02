# Glimpser Installation Guide

This guide provides detailed instructions for installing and setting up Glimpser on your system.

## System Requirements

- **Architecture**: Glimpser is primarily designed for x86 architecture.
  - ARM support may require additional work and is not guaranteed.
- **Operating System**: Linux (Ubuntu 20.04 LTS or later recommended)
- **Python**: Version 3.8 or higher

## Installation Steps

### 1. Clone the Repository

```sh
git clone https://github.com/yourusername/glimpser.git
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
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt-get update
sudo apt-get install -y google-chrome-stable
```

### 4. Install FFmpeg

FFmpeg is used for video processing in Glimpser:

```sh
sudo apt-get install -y ffmpeg
```

### 5. Install Python Dependencies

Install the required Python packages:

```sh
pip install -r requirements.txt
```

### 6. Set Up the Database

Initialize the local SQLite database:

```sh
python3 main.py
```

You will be prompted to create a secret key. Follow the guided setup to complete the database initialization.

### 7. Run the Application

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