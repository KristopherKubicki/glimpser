# Release Workflow

Glimpser packages are generated automatically when a version tag is pushed to the repository.
The process is split across multiple runners:

- **Ubuntu** builds the Debian package and runs the test suite. The packaging
  script now uses `rsync` to copy directories so unchanged files are skipped,
  speeding up repeated builds. It also reads the version from `pyproject.toml`
  to populate the Debian control file so releases stay in sync.
- **Windows** builds the standalone executable using `build_windows.py`.
- The build sets `GLIMPSER_SKIP_DB_INIT=1` to prevent database access during analysis.
- It also skips the optional `onnxruntime` package to avoid lengthy dependency scanning.
- **macOS** builds a self-contained application with `build_macos.py`.

The Ubuntu job also generates a small `release-badges.md` file that lists
status badges for the current tag. This file becomes the body of the GitHub
release so that each tagged version shows the latest CI status.

Both artifacts are attached to the GitHub release created for the tag. When the
`PYPI_API_TOKEN` secret is available, Python distributions are also published to
PyPI.

Tags are normally created automatically when the version in `pyproject.toml` is bumped
on the `main` branch. The `Tag Release` workflow runs
`scripts/auto_tag_release.py` to create a tag like `v0.2.8` and push it to
GitHub, which then triggers the build jobs above. Before tagging, the workflow
runs `scripts/update_version_files.py` so that `CITATION.cff` and the fallback
version in `app/config.py` stay aligned with the version from `pyproject.toml`.

Since the tag is pushed by a workflow, the job must grant `workflow: write`
permissions so that the subsequent release workflow is triggered.

You can still trigger a release manually by creating and pushing a tag:

```sh
git tag v0.2.8
git push origin v0.2.8
```

Alternatively, run `scripts/auto_tag_release.py` to create and push the tag
for the current version automatically.

## Troubleshooting

If the GitHub releases page still shows an older version than the footer,
the tag may not have been pushed. Run `scripts/auto_tag_release.py` again
or push the tag manually to publish the release and update the page.
