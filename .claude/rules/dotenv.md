---
paths:
  - "**/.env*"
---

# Dotenv rules

## Location

- `.env*` files live **next to their consumer**, not at the repo root. `services/api/.env`, `deploy/.env`, `tests/.env` — yes; root `.env` — only when the variable is genuinely shared by every workspace member.
- The repo-root `.env.example` is the legacy default and stays minimal.

## What to commit

- Commit only `.env.example`. Real `.env` files are gitignored.
- Every variable in `.env.example` carries an inline comment explaining what it is and showing a safe placeholder value.
- **No real secrets** — not even short-lived ones, not even in examples. Use `<replace_me>` / `example.com` / fake IDs.

## Format

- One `KEY=VALUE` per line. No surrounding quotes unless the value contains whitespace.
- Group related variables with a `# === Section name ===` header comment.
- Boolean flags use `true` / `false` literals, not `1` / `0`.

## Tooling

- Secret scanners (gitleaks, trufflehog, etc.) may flag values here. If they do, the example value is too realistic — replace with a clear placeholder like `<replace_me>` rather than bypassing the scanner.
