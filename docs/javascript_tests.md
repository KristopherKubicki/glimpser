# JavaScript Test Workflow

A dedicated GitHub Actions workflow runs the JavaScript test suite on every push and pull request targeting the `main` branch.

The job installs dependencies with `npm ci` and executes `npm test` using Node.js 20. Use this workflow to verify that any front-end code continues to build and test successfully.
