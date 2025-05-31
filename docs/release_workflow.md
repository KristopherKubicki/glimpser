# Release Workflow

Glimpser packages are generated automatically when a version tag is pushed to the repository.
The process is split across two runners:

- **Ubuntu** builds the Debian package and runs the test suite.
- **Windows** builds the standalone executable using `build_windows.py`.

Both artifacts are attached to the GitHub release created for the tag. When the
`PYPI_API_TOKEN` secret is available, Python distributions are also published to
PyPI.

Tags are normally created automatically when the version in `setup.py` is bumped
on the `main` branch.  The `Tag Release` workflow creates a tag like `v0.2.4`
and pushes it to GitHub, which then triggers the build jobs above.

You can still trigger a release manually by creating and pushing a tag:

```sh
git tag v0.2.4
git push origin v0.2.4
```

Alternatively, run `scripts/auto_tag_release.py` to create and push the tag
for the current version automatically.
