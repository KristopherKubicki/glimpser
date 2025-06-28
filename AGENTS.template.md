Scope: **`<subdir>`** only.
Follow project root coding standards.
Keep filenames slug-case, functions snake_case, classes CapWords.
New tests go next to code in `*_test.py`.
Prefer pure functions; minimise side-effects.
Use dependency injection instead of globals.
Import order: stdlib ▸ third-party ▸ local (enforced by `isort`).
Non-obvious regex / math needs a comment & unit test.
Avoid premature optimisation; measure first.
Update AGENTS.md if you add new conventions.
