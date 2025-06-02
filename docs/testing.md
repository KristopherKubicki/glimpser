# Testing and Coverage

Glimpser includes a comprehensive suite of unit tests. Run them with coverage to ensure your changes do not introduce regressions:

```sh
python -m coverage run -m pytest
python -m coverage html
```

The HTML report will be generated in `htmlcov/index.html`.

Before submitting a patch, lint the code with `flake8`:

```sh
flake8
```

Refer to [developer_guide.md](developer_guide.md) for setting up your environment.

Recent tests cover screenshot capture helpers, database initialization through
`TemplateManager`, and mocked OpenAI interactions.

## End-to-End Tests

The `tests/test_e2e_web.py` module contains basic browser tests. These tests
start the Flask server and drive a headless browser via Selenium. If a suitable
web driver is not available, the tests are automatically skipped.
