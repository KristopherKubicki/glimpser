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

## End-to-End Tests

The `tests/test_e2e_web.py` module contains browser-based scenarios powered by
Selenium. During the tests a Flask server is started in a background thread and
pointed at a temporary data directory. This creates an isolated SQLite
database so the tests do not interfere with your real data. The scenarios
currently covered are:

1. Opening the root URL redirects to `/login`.
2. The login page renders a form containing `username` and `password`
   fields.

Ensure that either **ChromeDriver** or **geckodriver** is installed and
available on your `PATH`. If Selenium cannot create a browser driver the tests
will be skipped automatically.

Run the end-to-end tests with:

```sh
pytest tests/test_e2e_web.py
```

Running the full suite with coverage (including the end-to-end tests) looks
like:

```sh
python -m coverage run -m pytest
python -m coverage html
```
