# AGENTS.md Usage Guide

This document explains how to use **AGENTS.md** files to guide agent behavior within this repository and other internal projects.

## Purpose of AGENTS.md

`AGENTS.md` files provide instructions or tips for automated agents working in a repository. They can specify coding conventions, how to run tests, or requirements for pull request messages. An `AGENTS.md` may live anywhere in a project tree and applies to all files under the directory where it resides. Instructions in more deeply nested `AGENTS.md` files override those higher up the tree.

Key points about `AGENTS.md`:

- The file's scope is the entire directory tree rooted at the folder that contains it.
- Every file touched by a change must obey relevant `AGENTS.md` instructions.
- Instructions apply only to code within the file's scope unless explicitly stated otherwise.
- More specific (`deeper`) `AGENTS.md` files take precedence if there are conflicts.
- Instructions from the current prompt supersede `AGENTS.md` content.
- These files might exist outside of Git repositories, such as in a user's home directory.
- If programmatic checks are specified, they **must** be run after code changes.

## Example Instructions

A typical `AGENTS.md` might include requirements such as:

```
Keep commits small and focused.
Use conventional commit messages.
Format code with black and/or prettier.
Run flake8 for lint checks.
Run tests with pytest.
Document major changes in docs/.
Summaries must cite changed files.
PR description must mention test results.
Explain complex logic in comments.
Each PR should have a single purpose.
```

An agent must read these instructions and follow them whenever modifying files within the relevant scope.

## Using AGENTS.md in This Organization

1. **Placement** – Add `AGENTS.md` files at meaningful directory levels. A file in the repository root applies to the whole project, while a nested file can refine rules for a subdirectory.
2. **Content** – Provide clear directions on coding style, commit practices, testing, or any other expectations for contributions.
3. **Precedence** – If multiple `AGENTS.md` files apply, the deepest one takes precedence. Keep this in mind when adding new guidelines.
4. **Running Checks** – When `AGENTS.md` specifies commands (lint, tests, etc.), the agent must run them after making changes and include the results in the pull request description.
5. **Documentation** – Place broader documentation about the organization's use of `AGENTS.md` in `docs/` so contributors know where to look.

## Summary

By using `AGENTS.md`, teams can embed instructions directly alongside code, ensuring that automated agents consistently apply the correct workflow, style, and testing requirements throughout the repository.
