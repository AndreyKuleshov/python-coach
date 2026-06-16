# QA pitfalls journal

A living registry of **test-side** pitfalls for this platform's test suite, in
`Symptom → Cause → Fix` form. Append new entries at the top, dated `YYYY-MM-DD`.
Remove an entry only when its cause is resolved in the product or framework.

This file is **data, not methodology** — open it on demand by symptom; do not
pre-load it. The `qa` agent appends a dated entry after each non-obvious
debugging session so the next run doesn't re-learn the same lesson.

Distinguish two kinds of entry:
- **Test-side pitfall** — a flake/locator/fixture/timing trap and how to write
  around it. These belong here.
- **Product bug** — a genuine defect in the API, sandbox runner, or frontend.
  Those go in `docs/bugs/` with the affected check `xfail`/`skip`'d; only a
  one-line cross-reference belongs here.

---

### 2026-06-12 — `RuntimeError: Event loop is closed` in async API tests

- **Symptom.** Async API tests driving the app over `ASGITransport` failed
  intermittently in teardown with `Event loop is closed` (asyncpg trying to
  close a pooled connection on a dead loop).
- **Cause.** The app's DB engine (`storage.db`) is a process-global lazily bound
  to the first event loop it sees. pytest-asyncio's default per-test loop closes
  those pooled connections out from under the global engine on the next test.
- **Fix.** Two parts, both test-side: (1) `asyncio_default_test_loop_scope =
  "session"` in `pyproject.toml` so the whole run shares one loop; (2) build a
  *test-owned* engine in a session-scoped fixture and point the app's
  `get_session` dependency at it via `app.dependency_overrides` — never reuse the
  production global engine across loops. Async fixtures that touch the DB must
  declare `loop_scope="session"` to match.

### 2026-06-12 — `from tests.conftest import` fails to collect

- **Symptom.** `ModuleNotFoundError: No module named 'tests'` at collection.
- **Cause.** The repo bans `__init__.py` in sub-packages (PEP-420), so `tests`
  is not an importable package; pytest's rootdir insertion only puts the test
  file's own directory on `sys.path`.
- **Fix.** Import shared helpers by bare module name (`from conftest import ...`,
  `from lesson_page import ...`) and add them to
  `[tool.ruff.lint.isort] known-first-party` so import order stays deterministic.

### Cross-references to product bugs (not test-side)

Both product bugs below are now FIXED by the `coder` agent; the test-side
guards that referenced them have been removed (the tests assert outright again).

- `docs/bugs/0001-sandbox-timeout-proc-kill-race.md` — FIXED. The `SandboxClient`
  timeout path now wraps `proc.kill()` in `contextlib.suppress(ProcessLookupError)`,
  so concurrent timeouts can no longer escape `run()`. The two timeout security
  tests (`test_infinite_loop_times_out_without_hanging`,
  `test_timeout_leaves_no_leaked_container`) no longer carry `xfail` and pass
  outright under `-n auto`.
- `docs/bugs/0002-static-dir-path-off-by-one.md` — FIXED. `_STATIC_DIR` now uses
  `parents[2]` and resolves to `services/api/static`, so `/` serves the lesson
  page. The UI scenarios in `tests/ui/test_lesson_flow.py` no longer carry the
  `skipif(not _STATIC_DIR.is_dir())` guard and run normally.

<!-- Template:
### YYYY-MM-DD — <one-line symptom title>

- **Symptom.** What you observed (the failing assertion, the timeout, the flake).
- **Cause.** The actual root cause, found by investigation — not a guess.
- **Fix.** The test-side change that resolves it, with a reusable rule for next time.
-->
