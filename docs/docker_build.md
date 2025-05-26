# Docker Build Verification

A dedicated GitHub Actions workflow builds the Docker image on every push and pull request. This step ensures that changes do not break the Dockerfile.

You can replicate the build locally with:

```sh
docker build -t glimpser .
```
