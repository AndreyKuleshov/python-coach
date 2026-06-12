---
paths:
  - "**/Makefile"
---

# Makefile rules

## Top-level vs domain Makefiles

- The **root `Makefile`** is a pure dispatcher: only `include` directives plus `.PHONY`/`.DEFAULT_GOAL`. No targets implementing real work — they live in domain Makefiles (`services/api/Makefile`, `tests/Makefile`, `deploy/Makefile`, etc.).
- Each domain Makefile is itself `include`-able from the root and self-sufficient when invoked directly from its own directory.

## Target naming

- Every target in a domain Makefile **must** be prefixed with the domain directory: `services/api/Makefile` exposes `api-*` targets, `tests/Makefile` — `tests-*`, `deploy/Makefile` — `deploy-*`. Without the prefix, targets collide in the root namespace when included.
- Exception: a domain may expose one short alias mirroring the prefix (e.g. `api: api-run`) — only when the domain has a single canonical "run" verb.

## Required boilerplate

- `.PHONY:` must list every non-file target.
- Use `-include .env` (soft) for env loading, never `include .env` (hard) — absence of `.env` must not break the build.
- Resolve repo paths via `REPO_ROOT := $(shell git rev-parse --show-toplevel)`. Never use relative `cd` for cross-directory work — `cd` chains break under `make -C` / parallel `-j`.

## Don't

- No shell logic in the root Makefile beyond `include`.
- No target without a prefix in a domain Makefile.
- No `@true` / `@:` "documentation-only" targets — write a comment instead.
