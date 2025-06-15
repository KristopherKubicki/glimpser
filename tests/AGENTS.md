# Test Guidelines

- Write new tests for every feature or bug fix.
- Use `pytest` for Python and Jest for JavaScript.
- Keep tests isolated by using fixtures.
- Run `flake8` and `pytest` (and `npm test` if JS tests change) before committing.
- The test environment has no network access after setup; design tests accordingly.
