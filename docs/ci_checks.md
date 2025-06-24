# Continuous Integration Checks

Glimpser runs automated quality checks on every push and pull request.
The workflow located at `.github/workflows/python-app.yml` performs the
following tasks:

- Formats Python code with `black` and lints with `flake8`.
- Lints JavaScript with `eslint` and verifies formatting with `prettier`.
- Executes `pytest` and `jest` test suites and uploads coverage.
- Coverage reports allow a small drop (up to 0.5%) before the Codecov check fails.
- Scans dependencies using `pip safety` and `npm audit`.
- Uses the built-in caching features of the setup actions and installs Node
  packages with `npm ci` for reproducible, faster builds.

These checks help catch regressions and security issues before code is merged.
