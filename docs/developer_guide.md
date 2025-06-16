# Glimpser Developer Guide

This guide provides tips for extending Glimpser, running tests, and contributing to the project.

## Setting Up a Development Environment

1. Clone the repository and create a virtual environment:
   ```sh
ruff check --exit-zero .
   git clone https://github.com/KristopherKubicki/glimpser.git
   cd glimpser
   python -m venv env
   source env/bin/activate
   ```
2. Install Python dependencies:
   ```sh
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
   Browser automation packages used for screenshots are grouped under the
   optional `browser` extras in `setup.py`. A minimal install only requires
   `wkhtmltoimage` for lightweight captures.
3. Set up tooling:
   ```sh
   make setup  # installs pre-commit hooks and JS packages
   ```
   After installation, verify hooks:
   ```sh
   pre-commit run --all-files
   ```
4. Copy the provided example environment file and update the values. Important
   variables include `SECRET_KEY` for session management, `CHATGPT_KEY` for AI
   features, and the various path settings used by the application.
   ```sh
   cp .env.example .env
   # edit .env before running the app
   ```
5. Install the Node.js dependencies used for CSS linting:
   ```sh
   npm install
   ```

## Understanding the Architecture

Before diving into new features, read
[Architecture Overview](architecture_overview.md). It describes how Flask routes,
background jobs and utility modules cooperate. The "Data Flow from Camera to UI"
section maps the path a captured frame takes through the scheduler and database
to the web interface.

## Running Tests

The project uses `pytest` for testing and lints Python with `ruff` and `flake8`. After activating your environment, run:

```sh
ruff check --exit-zero .
flake8
pytest
```

Running the full test suite helps ensure that your changes do not introduce regressions.

## Contribution Workflow

We follow a standard GitHub Flow:

1. Fork the repository and create a feature branch from `main`.
2. Make your changes and commit them with clear messages.
3. Ensure all tests pass and linting succeeds.
4. Open a pull request describing your changes.

For more details, see [CONTRIBUTING.md](https://github.com/KristopherKubicki/glimpser/blob/main/CONTRIBUTING.md).

## Extending the Codebase

- New routes can be added in `app/routes.py`.
- Utility functions live in `app/utils/`.
- Configuration defaults are defined in `app/config.py`.

When adding new features, include corresponding tests under the `tests/` directory.

- Utilities for network testing now have dedicated tests in `tests/test_network_testing_utils.py`.
- Configuration lookup logic is verified by `tests/test_config_get_setting.py`.
- Scheduler helpers are tested in `tests/test_scheduling_more.py`.
- Template update validation ensures numeric fields remain in range and
  required values are present.
- Forms validate input client-side with JavaScript and fall back to server-side checks.
- URLs in the template form must begin with http:// or https:// and fetch helpers provide consistent error handling.
- `save_template` now reschedules APScheduler jobs when a template is edited.
