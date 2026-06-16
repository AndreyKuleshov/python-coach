# Bug 0002 — static lesson page is never served (wrong `_STATIC_DIR` path)

**Severity:** high (the entire frontend is unreachable as shipped).
**Component:** `services/api/src/python_coach/app.py` (`_STATIC_DIR`).
**Status:** FIXED (2026-06-12) — `_STATIC_DIR` now uses `parents[2]` and resolves to
`services/api/static`, so `/` serves `index.html` and `/static` mounts. The UI scenarios no
longer carry the `skipif(not _STATIC_DIR.is_dir())` guard.

## Symptom

Running the API the documented way (`make api-run`, i.e. uvicorn from
`services/api`) and opening `/` returns `404 {"detail":"Not Found"}`. The
single-page lesson UI in `services/api/static/` is never mounted, so
`/` and `/static/*` do not exist.

Reproduced directly:

```text
$ uv run --directory services/api python -c \
    "from python_coach.app import _STATIC_DIR; print(_STATIC_DIR, _STATIC_DIR.is_dir())"
/Users/.../python-coach/services/static False
```

The `/` index route and the `/static` mount are guarded by
`if _STATIC_DIR.is_dir():`, so when the path is wrong they are silently skipped
and only the JSON API is served.

## Cause

`app.py` is at `services/api/src/python_coach/app.py`. Its parents are:

| index | path |
|---|---|
| parents[0] | `services/api/src/python_coach` |
| parents[1] | `services/api/src` |
| parents[2] | `services/api`  ← the `static/` dir lives here |
| parents[3] | `services`      ← currently used |

The code uses `parents[3]`:

```python
_STATIC_DIR = Path(__file__).resolve().parents[3] / "static"
```

which yields `services/static` (does not exist). It should be `parents[2]`.

## Fix (product change — not made by QA)

```python
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
```

(One-line off-by-one. After this, `/` serves `index.html` and `/static` mounts.)

## Test impact

The UI scenarios in `services/api/tests/ui/test_lesson_flow.py` need the page
served, so they are `skip`'d with a reference to this bug until the path is
fixed — collected but not run, never faked green. The page object and fixtures
are otherwise complete and were validated against a manually-mounted copy of the
static dir, so the moment the path is corrected the `skip` can be removed and
the scenarios should pass as written.
