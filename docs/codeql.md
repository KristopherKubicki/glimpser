# CodeQL Security Scanning

Glimpser performs static analysis with the GitHub CodeQL workflow.
The scan runs on every push, pull request, and weekly on a schedule.
Results are visible in the repository's **Security** tab and indicate
whether the analysis succeeded or failed. The workflow definition
is located at `.github/workflows/codeql.yml`.

The previous `codeql_old.yml` workflow has been removed to avoid
duplicate scans. All CodeQL analysis now runs through a single
pipeline defined in `codeql.yml`.
