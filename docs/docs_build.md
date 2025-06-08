# Docs Build Workflow

The `.github/workflows/docs-build.yml` workflow ensures documentation builds successfully on every push and pull request. It performs the following steps:

- Checks out the repository and sets up Python 3.x.
- Installs MkDocs using `pip`.
- Runs `mkdocs build --strict` to verify the documentation compiles without errors.

If the build step fails, the workflow prevents the PR from being merged.
