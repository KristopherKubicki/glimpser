# Dependency Review

Glimpser runs the GitHub [dependency-review-action](https://github.com/actions/dependency-review-action) on pull requests.
The workflow located at `.github/workflows/dependency-review.yml` scans dependency manifest changes and
flags known-vulnerable packages. When the check is required, pull requests introducing insecure
versions cannot be merged.

The job triggers on pull requests to the `main` branch and posts a summary comment in the PR with the
results.
