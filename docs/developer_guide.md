# Glimpser Developer Guide

This guide provides tips for extending Glimpser, running tests, and contributing to the project.

## Setting Up a Development Environment

1. Clone the repository and create a virtual environment:
   ```sh
   git clone https://github.com/KristopherKubicki/glimpser.git
   cd glimpser
   python -m venv env
   source env/bin/activate
   ```
2. Install the package in editable mode with development dependencies:
   ```sh
   pip install -e ".[dev]"
   ```
3. Install the `pre-commit` tool and set up the Git hooks:
   ```sh
   pip install pre-commit
   pre-commit install
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

## Running Tests

The project uses `pytest` for testing and `flake8` for linting. After activating your environment, run:
```sh
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

For more details, see [CONTRIBUTING.md](../CONTRIBUTING.md).

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
- `save_template` now reschedules APScheduler jobs when a template is edited.
