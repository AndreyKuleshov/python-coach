---
paths:
  - "services/api/**/*.py"
---

# Backend architecture — REST API layers

Layering for the REST API service (`services/api/src/`). Consult BEFORE adding or moving implementation code, or designing a new module. If a change cannot fit cleanly into these layers, stop and ask the user instead of inventing a new layer. Generic Python rules live in `python.md`; only API-specific layering is here.

## Layers

| Layer | What it contains |
|---|---|
| `transport/rest/` | FastAPI `APIRouter`s + request/response DTOs (Pydantic v2) + envelope shaping. A DTO is co-located with its route file until it grows large enough to split out. |
| `controllers/` | Use-cases — one module per route group. Receives **unpacked primitives** (DTO fields as kwargs, never DTO instances), orchestrates `storage` + `clients`. **Never imports `fastapi`.** |
| `storage/` | A single `Storage` class composed from per-domain mixins. Owns `session: AsyncSession`. ORM tables live in `storage/models/` and double as domain models. |
| `clients/` | External clients (one class per upstream — the sandbox/code-runner service, email, etc.). Same shape as `storage`, different name for semantics. Not "adapters". |

`src/`-layout: all Python code under `src/`, separate from `Makefile`, `Dockerfile`, `pyproject.toml`, `tests/`.

## Dependency rules (one direction only)

- `transport/rest` → `controllers` (via FastAPI deps) + its own DTOs. DTOs depend on nothing.
- `controllers` → `storage` + `clients`.
- `storage`, `clients` → never depend on layers above them.
- `deps.py` is the single stitching point: builds `Storage(session)`, resolves the current user, injects clients.

## Storage — one class, mixin-composed

```python
class Storage(LessonsMixin, ExercisesMixin, SubmissionsMixin, ProgressMixin):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
```

Transactions are native: `async with storage.session.begin(): ...`. No separate UnitOfWork.

## Controller input contract

A controller takes: unpacked primitives, `storage: Storage`, and the `clients` it needs. **Not** DTO instances, **not** a raw `AsyncSession`. It returns plain values or ad-hoc dataclasses; the route maps the result to a response DTO.

When a use-case needs an intermediate shape, define an ad-hoc `@dataclass` inside the same `controllers/<module>.py`. Do NOT create a parallel "domain models" layer mirroring the ORM tables.

## Decision table

| Adding… | Goes in |
|---|---|
| New endpoint | route + DTO in `transport/rest/<group>/<name>.py` + a method on the matching controller |
| New external service (e.g. sandbox runner) | new class in `clients/<name>.py`, injected via `deps.py` |
| New data domain | new mixin in `storage/_<domain>.py` + register it on `Storage` |
| Intermediate shape inside a use-case | ad-hoc `@dataclass` in the same controller module |

## Don't

- No `Protocol` / `ABC` for `Storage` or clients while there is exactly one implementation.
- No separate "domain models" layer alongside the ORM tables.
- No per-aggregate `*Repository` classes — `Storage` is the only repository surface.
- No cross-layer shortcuts (e.g. a route touching `storage` directly, or a controller importing `fastapi`).
- No new top-level layer without explicit user approval.
