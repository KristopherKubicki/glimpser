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

## Running Tests

The project uses `pytest` for testing and `flake8` for linting. After activating your environment, run:
```sh
flake8
pytest
```
Running the full test suite helps ensure that your changes do not introduce regressions.

### Test Fixtures

Reusable pytest fixtures are defined in `tests/conftest.py`. A helpful one is
`temp_media_dirs`, which creates temporary screenshot and video directories and
patches the configuration paths. Use it in your tests by accepting the fixture
as an argument:

```python
def test_something(temp_media_dirs):
    pass
```

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
