# Continuous Integration Checks

Glimpser runs automated quality checks on every push and pull request.
The workflows trigger when commits land on the `main` or `staging` branches
and on pull requests targeting those branches.
The workflow located at `.github/workflows/python-app.yml` performs the
following tasks:

- Formats Python code with `black`, sorts imports with `isort`, and lints with `ruff` and `flake8`.
- Checks type hints with `mypy`.
- Lints JavaScript with `eslint` and verifies formatting with `prettier`.
- Executes `pytest` and `jest` test suites and uploads coverage.
- Coverage reports allow a small drop (up to 0.5%) before the Codecov check fails.
- Scans dependencies using `pip safety` and `npm audit`.
- Caches Python and Node dependencies to speed up builds.

Running `pre-commit run --all-files` locally will execute the same Black,
isort, Flake8, and mypy checks before they fail in CI. These checks help catch
regressions and security issues before code is merged.
