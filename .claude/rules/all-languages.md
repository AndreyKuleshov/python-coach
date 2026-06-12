---
paths:
  - "**/*.{js,ts,tsx,go,py}"
---

# All-language rules

- Do not introduce abstractions (interfaces, protocols, base classes) until at least two concrete implementations exist. Inline first, extract later.
- Configuration values must be required — no default values in code. A missing env var should fail-fast on startup, not silently fall back.
- Comments, identifiers, branches, MR/PR titles, and commit messages: English only.
- Never use `print` / `console.log` / `fmt.Println` inside services. Services log through the configured logger. Console output is only for CLI tools and one-off local scripts.
- Every config field must come from an environment variable and must be required — no implicit defaults. Defaults breed silent drift between environments.
- Hard cap of ±500 lines per file. Beyond that, both humans and agents lose the thread — split semantically.
