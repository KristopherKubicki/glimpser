# Docker Build Verification

A dedicated GitHub Actions workflow builds the Docker image on pushes and pull requests targeting the `main` and `staging` branches. This step ensures that changes do not break the Dockerfile.

You can replicate the build locally with:

```sh
docker build -t glimpser .
```
