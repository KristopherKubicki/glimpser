# EthicalCheck Workflow

The `ethicalcheck.yml` workflow runs the free EthicalCheck action to test the API
specified in the configuration. It automatically scans the OpenAPI definition and
executes security tests for common vulnerabilities.

Results are uploaded as a SARIF file and sent to the configured email address.
This helps ensure that the API stays secure with every change.

The workflow triggers on pushes and pull requests to the `main` branch and also
runs weekly on Tuesday at 18:16 UTC. You can start it manually from the Actions
tab as well.

