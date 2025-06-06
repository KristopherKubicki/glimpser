1. Run `pre-commit run --all-files` before every push.
2. Code *must* pass `black --check` and `ruff` (or flake8) linting.
3. Docs *must* pass `mkdocs build --strict`; use `exclude_docs` not `exclude`.
4. Keep commits atomic: _one logical change, one commit_.
5. Use **Conventional Commits** for messages (e.g. `feat: …`, `fix: …`).
6. All public APIs require docstrings & type hints.
7. Update `CHANGELOG.md` and relevant docs for every PR.
8. PR description must include test run summary (`pytest -q`).
9. Complex logic ⇢ inline comments or ADR in `docs/architecture/`.
10. Tag reviewers before marking “ready for review”.
