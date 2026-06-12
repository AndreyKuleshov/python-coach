---
paths:
  - "**/*.py"
---

# Python style rules

## Tooling

- **`uv` only.** Never `pip`. Run scripts via `uv run`.
- **All configs live in `pyproject.toml`** (alembic, pytest, ruff, pyright). No `*.ini` files.

## Types

- Use built-ins: `list[int]`, `dict[str, int]`, `tuple[int, ...]`, `str | None`. Never import these from `typing`. `Any` is OK to import from `typing` when truly needed.
- **Always** annotate function arguments and return types.
- **Always** parameterise `dict` — `dict[K, V]`, never bare `dict` (the latter resolves to `dict[Unknown, Unknown]` and silences the type-checker).
- For multiple return values, use a `dataclass` (or `namedtuple` when the call is hot enough that dataclass overhead matters) — **not** a `tuple`, **not** a `dict`. Field names at the call site beat positional unpacking: future-you reading `outcome.player_id` understands the return shape without scrolling back to the producer. The only acceptable `tuple` returns are two scalars whose roles are obvious from naming context (e.g. `(x, y)` coordinates, `(key, value)` from an iterator helper) — and even then, prefer a dataclass when in doubt.

## Imports & layout

- **Absolute imports only.**
- **`__init__.py` — banned by default**, with one allowed exception: the workspace-member root (`services/<svc>/src/<svc>/__init__.py` or `packages/<pkg>/<pkg>/__init__.py`). Hatchling needs that one file to discover the package without an extra `src/` layer duplicating the package name in the import path; nowhere else needs it. **All sub-packages — `controllers/`, `transport/`, `storage/`, `clients/`, etc. — must be PEP-420 namespace packages (no `__init__.py`).** Imports work fine without it (`from svc.storage.storage import Storage`), and the absence forces the question "is there really a single canonical module to put here?" — usually the answer is no, and the directory just groups siblings. If you catch yourself creating a sub-`__init__.py` to host code, name the module explicitly (`storage/storage.py`, `clients/api.py`) and leave the directory init-free.

## Configuration

- Read env once at startup, validate with `pydantic-settings`, freeze. Don't sprinkle `os.getenv` across the codebase.

## Comments & docstrings

- **Every function gets a one-line docstring** — answer *why this exists*, not what it does (the body and the type signature already say what). For genuinely trivial helpers, one short sentence is enough; over-explaining hurts more than it helps.
- **Add a one-line comment above non-trivial code blocks.** If a block needs a paragraph of context to make sense at a glance — invariants, ordering constraints, surprising behaviour, a workaround — leave a hint. Don't paraphrase the code.
- Don't comment / docstring the obvious. `def total(items): """Sum item totals."""` adds nothing. Skip it.

## Control flow

- **Prefer early returns over nested `if`.** Validate inputs and bail out at the top; keep the happy path at the lowest indent. A function with three nested `if`-arrows is harder to follow than three guard clauses followed by linear code.

## Third-party libraries

- Reach for the `context7` MCP whenever you're unsure about a library's surface — don't invent APIs.
