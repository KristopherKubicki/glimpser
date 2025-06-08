# Pylint Checks

The workflow `.github/workflows/pylint.yml` runs Pylint on each push. It sets up a matrix of Python versions `3.8` through `3.12`. For every version it:

1. Checks out the repository.
2. Installs Pylint using `pip`.
3. Runs `pylint` against all tracked `.py` files with `--exit-zero` so the job succeeds even when warnings are reported.

The lint output appears in the Actions logs but does not fail the build.
