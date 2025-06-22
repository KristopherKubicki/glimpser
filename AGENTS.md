Keep commits small and focused.
Use conventional commit messages.
Format code with `black` and/or `prettier`
Run `flake8` for lint checks.
Run `pre-commit run --all-files`.
Run tests with `pytest`.
Use `pyproject.toml` for dependencies; do not use requirements files.
Use `npm test` for JavaScript changes.
Document major changes in `docs/`.
Summaries must cite changed files.
PR description must mention test results.
Explain complex logic in comments.
Each PR should have a single purpose.
Subdirectory `AGENTS.md` files must be no more than 10 lines.
