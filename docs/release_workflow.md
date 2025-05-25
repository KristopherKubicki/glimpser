# Release Workflow

Glimpser packages are generated automatically when a version tag is pushed to the repository.
The process is split across two runners:

- **Ubuntu** builds the Debian package and runs the test suite.
- **Windows** builds the standalone executable using `build_windows.py`.

Both artifacts are attached to the GitHub release created for the tag. When the
`PYPI_API_TOKEN` secret is available, Python distributions are also published to
PyPI.

To trigger a new release, create a tag and push it to GitHub:

```sh
git tag v1.0.0
git push origin v1.0.0
```
