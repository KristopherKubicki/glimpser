# Staged GitHub Flow

Our development workflow promotes changes in three lanes:

feature/topic branches – work in progress with draft pull requests
staging – the dress‑rehearsal branch
main – always deployable

```
                     ┌──────────────────────┐
feature/topic ──┬──▶ │      STAGING         │ ──┐
branches        │    └──────────────────────┘   │
(feature-x) ────┤                                │
(feature-y) ────┤                                ▼
(feature-z) ────┘                         ┌──────────────────────┐
                                          │        MAIN          │──▶ ● v0.3.6
                                          └──────────────────────┘
```

Developers can branch off anything and push freely. When a change is ready, retarget the pull request to **staging**. The PR must merge cleanly and pass all CI checks. Our CD pipeline deploys that exact commit to the staging environment. Once smoke tests remain green, the pipeline fast‑forwards the same artefact to **main**.

Direct commits to **main** are blocked to keep history linear and ensure the environment stays deployable. Tags are cut automatically whenever a commit reaches **main**. Hot-fixes follow the same path: branch off `main`, open a PR into `staging`, and let CI/CD promote the commit back to `main`.

The `.github/workflows/branch-protection.yml` workflow enforces this rule by
rejecting any push to `main` that does not originate from a merge of `staging`.

This unified flow simplifies rollbacks and removes manual steps from production pushes. For edge cases or questions, ping `@DevOps` in Slack.
