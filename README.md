<center>

  
  <source srcset="app/static/img/glimpser.png" media="(prefers-color-scheme: dark)">
  <img src="https://github.com/user-attachments/assets/6113370d-f15d-4195-8ae5-2cb748afbf46" alt="Use dark mode!">


</center>

# Glimpser

[![Python application](https://github.com/KristopherKubicki/glimpser/actions/workflows/python-app.yml/badge.svg)](https://github.com/KristopherKubicki/glimpser/actions/workflows/python-app.yml)
[![Pylint](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml/badge.svg)](https://github.com/KristopherKubicki/glimpser/actions/workflows/pylint.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)
[![GitHub release](https://img.shields.io/github/v/release/KristopherKubicki/glimpser)](https://github.com/KristopherKubicki/glimpser/releases/latest)
[![Coverage](https://codecov.io/gh/KristopherKubicki/glimpser/branch/main/graph/badge.svg)](https://codecov.io/gh/KristopherKubicki/glimpser)

## Introduction
Glimpser is a straightforward yet powerful real-time monitoring application designed to capture, analyze, and summarize live data from various sources such as cameras, dashboards, and video streams. Utilizing advanced image processing techniques and AI models, Glimpser provides insightful summaries and alerts. It’s highly configurable, allowing users to tailor it to their specific monitoring needs through an easy-to-use interface.

For more documentation, see the [documentation index](docs/index.md).
You can find an overview of the docs folder in [docs/README.md](docs/README.md).
Read a high-level [Architecture Overview](docs/architecture_overview.md) to understand how the pieces fit together.

![Glimpser August 2024](https://github.com/user-attachments/assets/44ddcbd5-31f1-4ff9-954a-954a85479dc0)

## Features
- **Real-time Monitoring**: Continuously captures data from multiple sources. Whether it's a traffic camera or a weather dashboard, Glimpser ensures you’re always up-to-date with the latest information.

- **Image Processing**: Employs advanced techniques to compare images and detect even subtle changes, making it ideal for monitoring evolving situations effectively.

- **Motion Detection**: Automatically detects motion in the captured images and videos, triggering alerts and actions as configured by the user.

- **AI Integration**: Integrates with models like ChatGPT to provide intelligent insights. It can summarize data, detect anomalies, and generate alerts based on predefined rules.

- **Auto-captioning**: Automatically generates concise and informative captions for images and videos, providing quick insights into the content.

- **Auto-summarization**: Summarizes data from multiple sources into a coherent and concise format, highlighting the most important information.
- **RTSP Streaming**: Exposes a basic RTSP endpoint (`/test.rtsp`) so external NVRs can ingest the MJPEG stream. Supported verbs are `OPTIONS`, `DESCRIBE`, `SETUP`, `PLAY`, `PAUSE`, `GET_PARAMETER`, and `TEARDOWN`.

- **Customizable Configuration**: Easily configure different data sources and processing rules through the user-friendly interface. Glimpser’s configuration is fully database-driven, ensuring flexibility and ease of use.

- **Data Retention Policies**: Automatically manages storage by cleaning up old data, ensuring the system remains efficient without requiring constant manual intervention.
- **HTTP Callbacks**: When a template specifies a callback URL, Glimpser sends a
  JSON webhook with caption or motion updates to that endpoint. See the
  [HTTP Callback Guide](docs/http_callbacks.md) for setup details and payload
  examples.
- **SMS Alerts**: Configure Twilio credentials to receive important notifications by text message.
 - **Camera Discovery**: Use the `/discover` page to automatically scan the local network for ONVIF, RTSP, RTMP, HTTP/MJPEG, HLS, and SSDP devices. The table now displays each camera's MAC address and manufacturer when available.
- **Camera Fix Suggestions**: Validate a template and discover alternative URLs with `/suggest_fix/<template>`. See [Camera Fix Suggestions](docs/camera_fix.md).
- **Local Cameras**: `/discover` also lists any available `/dev/video*` devices for easy webcam integration.

- **Web Interface**: A user-friendly web interface allows for easy monitoring and configuration. Users can view live feeds, summaries, and configure settings without delving into the code.

## Installation

### Prerequisites
- Python 3.8 to 3.11

### Steps
1. **Install the Package**
   ```sh
   pip install glimpser
   ```

   Or, if you want to install from source:
   ```sh
   git clone https://github.com/KristopherKubicki/glimpser.git
   cd glimpser
   pip install .
   ```

2. **Run the Application**
```sh
glimpser
```

You can pass command-line options to customize the runtime configuration. The most
common flags are:

```sh
# Start without the background scheduler
glimpser --no-scheduler

# Skip scheduling crawler jobs
glimpser --no-crawlers

# Disable the watchdog thread
glimpser --no-watchdog
```

Run `glimpser --help` to see all available options.

For a full description of every command-line flag, including the separate credentials utility, see [docs/command_line.md](docs/command_line.md).

   You will be prompted to create a secret key to initialize the local sqlite database. Follow the rest of the guided setup and then direct your browser to http://127.0.0.1:8082 to finish the rest of the setup.

### Docker Quick Start

If you prefer to run Glimpser in Docker, copy `.env.example` to `.env` and set at least `SECRET_KEY` and `API_KEY`. You may also adjust `SESSION_TIMEOUT_MINUTES` and related cookie settings. Then build and start the container using Gunicorn:

```sh
docker-compose up --build
```

The web interface will be available at [http://localhost:8082](http://localhost:8082).

## Usage

### Configuration
Glimpser uses a database-driven configuration to manage data sources and processing rules. Users can easily add, update, or remove configurations through the web interface. SMS alerts can be enabled by setting `TWILIO_SID`, `TWILIO_TOKEN`, and `TWILIO_NUMBER` in the configuration.

### Capturing Screenshots
The preferred method for capturing screenshots is through the Glimpser web interface. Simply navigate to the capture section, select your desired source, and click the capture button. This ensures a seamless and user-friendly experience.

### Running Tests
To ensure everything works as expected, you can run the included unit tests:
```sh
python -m coverage run -m pytest
```

### Motion Detection
Glimpser automatically detects motion in the captured images and videos. When motion is detected, the system can trigger alerts, capture additional data, and generate relevant summaries and captions.

### Auto-captioning
Using advanced AI models, Glimpser generates concise and informative captions for images and videos. This feature helps users quickly understand the content and context of the captured data.

### Auto-summarization
Glimpser can summarize data from multiple sources into a coherent and concise format. The summaries highlight the most important information, making it easier for users to stay informed.

### RTSP Streaming
Glimpser exposes a simple RTSP endpoint at `/test.rtsp`. When a client issues the standard RTSP verbs, the `/rtsp_stream` route serves MJPEG frames packetized with RTP headers.

Typical sequence:

1. `OPTIONS`
2. `DESCRIBE`
3. `SETUP`
4. `PLAY`
5. (optional) `PAUSE` / `PLAY`
6. Periodic `GET_PARAMETER` to keep the session alive
7. `TEARDOWN` to close the session

This allows external NVR software to ingest the stream as a basic camera source.

## Development

To set up the project for development:

1. Clone the repository:
   ```sh
   git clone https://github.com/KristopherKubicki/glimpser.git
   cd glimpser
   ```

2. Create a virtual environment and activate it:
   ```sh
   python -m venv env
   source env/bin/activate  # On Windows, use `env\Scripts\activate`
   ```

3. Install the package in editable mode with development dependencies:
   ```sh
   pip install -e ".[dev]"
   ```

4. Run tests:
   ```sh
   pytest
   ```

## Releases
Release packages are built automatically when a version tag is pushed.
The workflow runs tests and creates the Debian package on an Ubuntu runner.
The Windows executable is built separately on a Windows runner using
`build_windows.py`. When both steps finish, the resulting Debian package and
Windows binary are uploaded to the GitHub release for that tag.
If the repository contains a `PYPI_API_TOKEN` secret, the workflow also
builds Python distributions and publishes them to PyPI. These files can be
downloaded from the Releases page or installed with `pip`.

## Contributing
Contributions are always welcome. If you have an idea to improve Glimpser, feel free to fork the repository and submit a pull request. Please read our [Code of Conduct](CODE_OF_CONDUCT.md) to understand the expectations for participants and how to report issues.

### Steps to Contribute
1. Fork the repository.
2. Create a feature branch.
    ```sh
    git checkout -b feature-branch
    ```
3. Commit your changes.
    ```sh
    git commit -m "Description of changes"
    ```
4. Push to the branch.
    ```sh
    git push origin feature-branch
    ```
5. Open a pull request.

## Recommendations
For detailed suggestions on how to use Glimpser effectively, please check out our [Recommendations](docs/recommendations.md) guide.

## License
This project is licensed under the MIT License. See the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgements
We are grateful to the contributors and the open-source community. Special thanks to OpenAI for their powerful models that enable Glimpser's advanced features.
