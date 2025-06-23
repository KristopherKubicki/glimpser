# Pylint Checks

Pylint runs as part of the [`python-app.yml`](../.github/workflows/python-app.yml)
workflow. After dependencies install, the step executes:

```bash
pylint $(git ls-files '*.py') --exit-zero
```

Warnings do not fail the build, but the output appears in the Actions logs.
