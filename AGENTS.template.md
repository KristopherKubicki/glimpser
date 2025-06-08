1. Scope: **`<subdir>`** only.
2. Follow project root coding standards.
3. Keep filenames slug-case, functions snake_case, classes CapWords.
4. New tests go next to code in `*_test.py`.
5. Prefer pure functions; minimise side-effects.
6. Use dependency injection instead of globals.
7. Import order: stdlib ▸ third-party ▸ local (enforced by `isort`).
8. Non-obvious regex / math needs a comment & unit test.
9. Avoid premature optimisation; measure first.
10. Update this guide if you add new conventions.
