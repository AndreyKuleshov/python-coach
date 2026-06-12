---
paths:
  - "**/Dockerfile*"
---

# Dockerfile rules

Universal best practices — no project-specific opinions. If something here
becomes a contested choice for a given service, override it locally.

## Pin and isolate

- **Never use the `latest` tag** for base images. Pin a specific version
  (digest or `name:tag`); a moving target makes builds non-reproducible.
- **Multi-stage builds** for anything that has a build step. The runtime
  stage must not contain compilers, build toolchains, or dev dependencies.

## Layer ordering

- Order `COPY` / `RUN` instructions from least- to most-volatile: system
  packages → dependency manifests (lock files) → application code. Lock
  files belong in their own `COPY` so dependency installation caches
  independently of source changes.

## Run as non-root

- Create a dedicated unprivileged user and `USER` to it before the
  entrypoint. Containers running as root violate least-privilege and most
  hardened orchestrators reject them.

## Hygiene

- Combine `apt-get update` with `apt-get install` in a single `RUN` and
  clean apt lists in the same layer; otherwise stale package metadata
  bloats the image.
- Set `WORKDIR` explicitly; don't rely on the implicit `/` working
  directory.
