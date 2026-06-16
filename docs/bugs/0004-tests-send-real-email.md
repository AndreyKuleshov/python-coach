# Bug 0004 — the test suite sent real confirmation emails

**Severity:** high (side effects / spam) — running the suite dispatched real mail
via the configured SMTP, flooding the owner's inbox with bounce-backs.
**Component:** `services/api/tests/conftest.py`, `services/api/tests/ui/conftest.py`
(test harness vs `clients/email.py` + `transport/deps.py`).
**Status:** FIXED (2026-06-16) — tests never reach real SMTP now, independent of
the ambient `.env`.

## Symptom
After real SMTP was configured in `services/api/.env`, running `pytest` produced
dozens of "Confirm your python-coach account" bounce emails to addresses like
`qa-main-*@example.com` / `qa-b-*@example.com` — i.e. the test fixtures' users.

## Cause
Auth tests call `POST /api/auth/register`; the in-process app reads the real
`.env`, so `EmailClient` saw `SMTP_HOST` set and actually sent via Gmail. The old
conftest comment ("SMTP is unset in tests") was a fragile assumption that broke
the moment a developer configured real SMTP locally.

## Fix
- In-process API tests override `get_email_client` with a recording `_FakeEmailClient`
  (no SMTP) for the whole session — the guarantee no longer depends on `.env`.
- The UI live-server subprocess is launched with `SMTP_HOST=""` (+ blank SMTP user/pass)
  so its real `EmailClient` takes the log-fallback path.
- Safety regression `test_register_uses_fake_email_client_not_smtp` fails if the
  override regresses.

The `:8077` dev server still sends real mail for actual users — only tests are gagged.
