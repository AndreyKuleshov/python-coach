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

_No entries yet. The first real debugging lesson goes here._

<!-- Template:
### YYYY-MM-DD — <one-line symptom title>

- **Symptom.** What you observed (the failing assertion, the timeout, the flake).
- **Cause.** The actual root cause, found by investigation — not a guess.
- **Fix.** The test-side change that resolves it, with a reusable rule for next time.
-->
