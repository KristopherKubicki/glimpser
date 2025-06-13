# OWASP Dependency Check

Glimpser scans third‑party packages with the OWASP Dependency‑Check action.
The workflow defined in `.github/workflows/dependency-check.yml` runs on every
push and pull request. It fails the build if vulnerabilities with a CVSS score
of 7.0 or higher ("High" severity) are detected. The SARIF report and a
CycloneDX SBOM are uploaded as workflow artefacts.
