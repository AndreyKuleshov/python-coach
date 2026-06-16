# Bug 0003 — login form could render without being hidden (auth modal)

**Severity:** low (UI correctness) — a logged-out visitor could see a stray form.
**Component:** `services/api/static/index.html` (auth modal `#login-form`).
**Status:** FIXED (2026-06-12) — `#login-form` now carries its own `class="hidden"`
so it is hidden by default and only `showLoginForm()` reveals it.

## Symptom
On the lesson page a logged-out user could see auth sub-forms rendered together
(login + register + "check your email") instead of exactly one. (A separate
contributor to the original report was a stale browser cache serving an old
`app.js`; a hard refresh resolved that part. This entry covers the real code
defect.)

## Cause
`#login-form` had no `class="hidden"` of its own and relied solely on the parent
modal's hidden state. If the modal was shown without `showLoginForm()` running
first, the form leaked (its siblings `#register-form`/`#confirm-pending` were
correctly `hidden`).

## Fix
Declare the login form's own hidden state. Added 8 regression tests in
`tests/ui/test_visibility.py` pinning the invariants the prior UI tests missed:
exactly one content view visible at a time, modal hidden on load, only the active
sub-form shown, and titles rendered as localized strings (not `[object Object]`).
