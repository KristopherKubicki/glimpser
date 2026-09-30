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

The platform artifacts are attached to the GitHub release created for the tag. When the
`PYPI_API_TOKEN` secret is available, Python distributions are also published to
PyPI.

Tags are normally created automatically when the version in `pyproject.toml` is bumped
on the `main` branch. The `Tag Release` workflow runs
`scripts/auto_tag_release.py` to create a tag like `v0.2.9` and push it to
GitHub. It then explicitly dispatches the build jobs above. Before tagging, the workflow
runs `scripts/update_version_files.py` so that `CITATION.cff` and the fallback
version in `app/config.py` stay aligned with the version from `pyproject.toml`.

The tagging job uses `contents: write` to push the tag and `actions: write` to
explicitly dispatch `release-packages.yml` at that tag. A tag pushed with
`GITHUB_TOKEN` does **not** trigger another workflow's `push` event;
`workflow_dispatch` is an explicit exception. See
[GitHub's token event rules](https://docs.github.com/en/actions/concepts/security/github_token).
No personal access token is required.

Version detection reads `[project].version` with Python's TOML parser. It must
not match a separate `[tool.commitizen].version` or depend on whitespace.
Release scripts and the tagging runner use Python 3.11 or newer.

## Before a point release

1. Reconcile deployed source with the candidate Git commit. Include dependencies
   and regression tests for the fixes; exclude credentials, databases, captures,
   local backups, and machine-specific configuration. A healthy deployed service
   is not proof that GitHub contains the same code.
2. Run affected tests, required repository checks, and package builds against
   that exact candidate. Record remaining capacity or feed failures in the notes.
3. Update `[project].version` and the Commitizen version together; run
   `python scripts/update_version_files.py` and review the resulting diff.
4. Verify the version without creating a tag:
   `python scripts/auto_tag_release.py --print-version`.
5. Merge only the reviewed release candidate. The tagging workflow then dispatches
   package builds for the version tag. Verify the run and attached artifacts
   before announcing the release.

If tagging succeeds but the dispatch fails, rerun the tagging job. Existing tags
are left intact and the build dispatch is retried. To retry only packaging, run
`gh workflow run release-packages.yml --ref vX.Y.Z` for the intended existing tag.
A manual build on a branch validates builds but does not publish tag assets.

You can still trigger a release manually by creating and pushing a tag:

```sh
git tag v0.2.9
git push origin v0.2.9
```

Alternatively, run `scripts/auto_tag_release.py` to create and push the tag
for the current version automatically.

## Troubleshooting

If the GitHub releases page still shows an older version than the footer,
the tag may not have been pushed. Run `scripts/auto_tag_release.py` again
or push the tag manually to publish the release and update the page.
