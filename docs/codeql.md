# CodeQL Security Scanning

Glimpser performs static analysis with the GitHub CodeQL workflow.
The scan runs on every push, pull request, and weekly on a schedule.
Results are visible in the repository's **Security** tab and indicate
whether the analysis succeeded or failed. The workflow definition
is located at `.github/workflows/codeql.yml`.
