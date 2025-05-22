# Glimpser Architecture Overview

This document provides a high level overview of the major components of Glimpser and describes how data flows from capture to summary.

## Key Components

- **Web server (`app/routes.py`)**: Flask application that exposes the web interface and REST API. It handles user authentication, template management, status pages, and endpoints for retrieving screenshots and summaries.
- **Utility modules (`app/utils/`)**: Collection of helpers responsible for capturing data, processing images, interacting with LLMs, and scheduling jobs. Important modules include:
  - `screenshots.py` – capture or download screenshots and video frames.
  - `image_processing.py` and `detect.py` – analyze images and detect motion.
  - `llm.py` – generate captions and summaries using language models.
  - `scheduling.py` – orchestrate periodic jobs via APScheduler.
  - `db.py` – initialize the SQLite database connection.
- **Scheduler**: The background APScheduler instance defined in `scheduling.py` runs capture and summarization jobs on a defined interval.
- **Database**: A lightweight SQLite database stores template details and other persistent metadata.

## Data Flow

1. **Template Configuration** – Users define capture templates in the web interface. Each template specifies the source to capture and how frequently it should run.
2. **Scheduled Capture** – The scheduler triggers `update_camera` for each template. `screenshots.py` grabs an image or frame based on the template settings.
3. **Processing and Detection** – Captured data is analyzed with `detect.py` and `image_processing.py`. When motion or changes are detected, captions are generated with `llm.py`.
4. **Database and Storage** – Metadata is written to the database while screenshots and videos are saved under the `data/` directory.
5. **Summaries** – Periodically, `update_summary` compiles recent captions and uses the language model to generate a textual summary saved in `data/summaries/`.
6. **Presentation** – Routes in `app/routes.py` serve screenshots, summaries, and system status through the web interface and API.

This flow allows Glimpser to continuously monitor sources, analyze results, and provide human‑readable summaries.
