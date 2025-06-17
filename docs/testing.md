# Testing and Coverage

Glimpser includes a comprehensive suite of unit tests. Run them with coverage to ensure your changes do not introduce regressions:

```sh
python -m coverage run -m pytest
python -m coverage html
```

The HTML report will be generated in `htmlcov/index.html`.

Before submitting a patch, lint the code with `ruff` and `flake8`:

```sh
ruff check --exit-zero .
flake8
```

Refer to [developer_guide.md](developer_guide.md) for setting up your environment.

Recent tests cover screenshot capture helpers, database initialization through
`TemplateManager`, and mocked OpenAI interactions.

All tests run with `pytest-socket` active, preventing any outbound network
requests. If a scenario truly requires network access call
`pytest_socket.enable_socket()` within that test.

Even the optional end-to-end tests run with sockets disabled unless they
explicitly enable them.

Pytest ignores the Debian packaging directory. Running `build_packages.sh`
creates a copy of the app under `debian/glimpser`, but `norecursedirs`
prevents those files from being collected as tests.

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

End-to-end tests are skipped by default. To run them set `SKIP_E2E=0` and use:

```sh
pytest tests/test_e2e_web.py
```

Running the full suite with coverage, including the end-to-end tests, looks
like:

```sh
python -m coverage run -m pytest
python -m coverage html
```

## JavaScript Unit Tests

Front‑end utilities under `app/static/js` are tested with **Jest**. The tests
use the JSDOM environment so that DOM APIs are available in Node. Run them with coverage enabled:

```sh
npm test -- --coverage
```

Jest runs in ESM mode because `package.json` declares `"type": "module"`.
Dynamic imports work without additional configuration.

New tests cover automatic Service Worker registration and template helpers.

## Playwright End‑to‑End Tests

For critical user flows a minimal Playwright setup lives in
`tests/playwright`. These tests start the development server defined in
`playwright.config.js` and drive a headless browser. Execute them with:

```sh
npx playwright test
```

Playwright is optional, so the Node dependencies are not included in the
repository. Install them locally to run the tests.
