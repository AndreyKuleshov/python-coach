# Bug 0007 — Grader returns misleading "no tests collected" on SyntaxError/ImportError

**Severity:** high (usability) — a learner whose code has a syntax or import
error receives a cryptic runner message that implies a framework misconfiguration
("check the test filename") instead of the actual Python error they must fix.
**Component:** `services/sandbox/runner/run_tests.py` (`_Collector` plugin,
`main()`).
**Status:** FIXED (2026-06-17) — collection failures are now captured in a
dedicated `pytest_collectreport` hook; `main()` checks them first and prefixes
the real traceback with "Your code could not be loaded:" so the learner sees the
SyntaxError or ImportError directly.

## Symptom

Submitting code with a syntax error (e.g. `return x +` with no right-hand
operand) yields:

```json
{
  "status": "error",
  "runner_error": "Ошибка запуска: no tests collected (check the test filename)",
  "tests": []
}
```

The "no tests collected" message refers to a misnamed test file, but the real
cause is a SyntaxError in `solution.py`. The learner has no information about
what to fix.

## Cause

The `_Collector` plugin only implemented `pytest_runtest_logreport`, which fires
once per test during the run phase. When `solution.py` contains a SyntaxError,
pytest raises a collection error while importing the test file (which does
`from solution import ...`). This collection failure produces a `CollectReport`
with `report.failed = True`, but since no tests are ever scheduled, no
`TestReport` is issued. The runner therefore sees an empty `collector.tests`
list and falls into the catch-all branch:

```python
runner_error = "no tests collected (check the test filename)" if not collector.tests else ""
```

The real traceback was available in `report.longrepr` but was never captured.

## Fix

Two changes in `services/sandbox/runner/run_tests.py`:

1. Added `pytest_collectreport(self, report)` hook to `_Collector` that appends
   `_shorten(str(report.longrepr))` to a new `self.collection_errors` list for
   every failed collect report.

2. Changed the `runner_error` decision in `main()` to a priority order:
   - If `collector.collection_errors` is non-empty → `passed = False` and
     `runner_error = "Your code could not be loaded:\n" + collection_errors[0]`.
   - Else if no tests collected → keep existing "no tests collected …" message.
   - Else → normal pass/fail result with `runner_error = ""`.

The sandbox image was rebuilt (`make sandbox-build`) for the fix to take effect.
