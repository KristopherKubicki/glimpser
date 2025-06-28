# Docker Build Verification

A dedicated GitHub Actions workflow builds the Docker image on every push and pull request. This step ensures that changes do not break the Dockerfile.

The Dockerfile now uses multiple stages and installs a pinned `uv` binary for dependency management. Build the final image locally with:

```sh
docker build -t glimpser .
```
