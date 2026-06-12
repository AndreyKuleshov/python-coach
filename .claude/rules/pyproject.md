---
paths:
  - "**/pyproject.toml"
---

# pyproject.toml rules

Before changing this file or any dependency declaration in any `pyproject.toml` — consult `.claude/rules/stack.md`.

## Build system

- **Hatchling only** for workspace members:
  ```toml
  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"
  ```
- Never use poetry, setuptools, flit, or pdm-backend in this repo.
- Wheel packaging is explicit: `[tool.hatch.build.targets.wheel] packages = ["<pkg>"]` — list every package directory the member exports.

## Dependency declaration

- Runtime deps go in `[project.dependencies]`.
- Dev/test deps go in `[dependency-groups] dev = [...]` (PEP 735). **Never** `[project.optional-dependencies]` for dev tooling.
- Pin sentinels: `>=X.Y,<Z+1` for third-party libs. Workspace members reference each other via `[tool.uv.sources] <pkg> = { workspace = true }`.

## Python version

- `requires-python = ">=3.13"` in every member, consistent with the repo `.python-version`.

## Tool configuration

- Linter / type-checker / test runner configs (`[tool.ruff]`, `[tool.pyright]`, `[tool.pytest.ini_options]`) live inside the member's `pyproject.toml`, never in standalone `*.ini` / `*.cfg` files.
- `target-version = "py313"` in the ruff section.

## Don't

- No bare `pyproject.toml` without `[build-system]` for a workspace member that exports code (only the workspace root may be source-less).
- No tool sections that duplicate root settings — inherit from the workspace where possible.
