# python-coach

A personal, interactive platform for learning advanced Python with a
test-automation (AQA) focus. Read a lesson → write Python in the browser →
submit → the server grades it with **pytest in an isolated Docker sandbox** →
see structured results and progress.

> **Status: Stage-1 MVP skeleton.** Infrastructure + storage contract only. The
> single seeded lesson is a **throwaway placeholder** to prove the pipeline —
> real lessons are authored by the methodist agent against
> [`STORAGE_CONTRACT.md`](./STORAGE_CONTRACT.md). See [`CONTEXT.md`](./CONTEXT.md).

## Architecture

```
services/api/                 FastAPI app (uv workspace member)
  src/python_coach/
    app.py                    ASGI entrypoint, routers, static page, logging
    settings.py               pydantic-settings (env-only, frozen)
    transport/                FastAPI routers + DTOs + deps.py (the wiring point)
      rest/{auth,lessons,submissions,progress,profile}/routes.py
      deps.py                 builds Storage/clients + resolves the current user (JWT)
    controllers/              use-cases; take unpacked primitives; no fastapi import
      auth.py, security.py    register/confirm/login + Argon2 hashing + JWT helpers
      lessons.py              lesson reads + completion/unlock fold (the gate)
      profile.py              profile/progress aggregate (reuses the lessons fold)
    storage/                  one Storage class, per-domain mixins, SQLModel tables
      models/{lesson,submission,user}.py
    clients/                  SandboxClient (Docker runner) + EmailClient + result dataclasses
    migrations/               Alembic (config in pyproject, no alembic.ini)
    seed.py                   lesson ingest CLI (the methodist's tool)
  static/                     single-page UI: i18n.js, auth.js, app.js, profile.js (CDN CodeMirror + marked)
  tests/                      pytest
services/sandbox/             Docker image that runs ONE submission's pytest
  Dockerfile, runner/run_tests.py, smoke.sh
deploy/                       docker-compose for local Postgres
fixtures/                     placeholder_lesson.json (THROWAWAY)
```

Layering (enforced by **import-linter**): `transport → controllers →
storage/clients`; lower layers never import upward; controllers never import
fastapi. See `.claude/rules/api-layers.md`.

## DB schema

`lesson` 1—∞ `exercise` 1—∞ `exercise_test`. `user` 1—∞ `submission` /
`progress`: both carry a `user_id` FK and progress is unique per
`(user_id, exercise_id)` (per-account attempt counters + solved flags).
Timestamps are `TIMESTAMP WITH TIME ZONE`. `submission.result` is JSONB holding
the structured pytest verdict. Full field reference:
[`STORAGE_CONTRACT.md`](./STORAGE_CONTRACT.md).

## Authentication & per-user progress

Login is **email + password** with **email confirmation required** before login.

- `POST /api/auth/register {email, password}` — creates an **unconfirmed** user
  (password hashed with **Argon2id** via `argon2-cffi`) and sends a confirmation
  link. **If SMTP is not configured (`SMTP_HOST` empty), the link is logged**
  via structlog (`event=email.confirmation_link`) so you can confirm locally
  without SMTP creds. Password must be ≥ 8 chars.
- `GET /api/auth/confirm?token=...` — verifies the link (a short-lived
  purpose-tagged **JWT**, so there is no token table) and confirms the email;
  returns a friendly HTML page.
- `POST /api/auth/login {email, password}` — verifies the Argon2 hash; an
  unconfirmed account is **403**; a confirmed one gets a **JWT bearer access
  token** (`{access_token, token_type, expires_at}`).
- `GET /api/auth/me` — the current user, resolved from `Authorization: Bearer`.

**Protected — everything content-related** (require the bearer token;
a request without/with an invalid token → **401**):
`GET /api/lessons`, `GET /api/lessons/{slug}`, `POST /api/submissions`,
`GET /api/submissions/{id}`, `GET /api/progress/{id}`, `GET /api/profile`. Lesson
reads, submissions, progress, and the profile are all keyed to the current user.
**Public — the only unauthenticated endpoints:** the auth routes above
(`register`, `confirm`, `login`; `me` resolves the token).

## Progression: completion, sequential unlock, profile

Learning is a guided sequence enforced **server-side** (the frontend mirrors,
never replaces, the gate):

- **Completion is derived** (no stored flag): a lesson is completed when it has
  exercises and the user has a solved `Progress` row for every one of them.
- **Sequential unlock** over published lessons ordered by `position`: the first
  is always unlocked; each later one unlocks once the previous published lesson
  is completed. `GET /api/lessons/{slug}` returns **403** for a locked lesson
  (no content served) and `POST /api/submissions` returns **403** for an exercise
  in a locked lesson.
- `GET /api/lessons` returns each published lesson with `is_completed` /
  `is_unlocked` (plus slug/title/position). The single-lesson read adds
  `is_completed` and `next_slug` (the next published lesson by position, or null
  if last) to drive the "Next lesson →" button.
- `GET /api/profile` returns the user's email, an ordered list of all published
  lessons each with `{slug, title, position, total_exercises, solved_exercises,
  is_completed, is_unlocked}`, and totals (`lessons_completed` /
  `lessons_total`). Reachable in the UI at `/profile` (the account email in the
  header links to it).

Frontend routes: `/lessons` (list with completed ✓ / current / locked rows —
locked rows are not clickable), `/?lesson=<slug>` (lesson view; a locked deep
link redirects to `/lessons` with a hint, since the API answers 403), and
`/profile` (progress bar + per-lesson status). All bilingual EN/RU.

The frontend stores the JWT in `localStorage` and attaches it on every content
call. **No content is reachable while logged out:** the landing `/` shows the
inline login/register form, the lessons list is its own authenticated view at
`/lessons` (a backend SPA catch-all serves the shell so the JS router resolves
it), and any logged-out deep link redirects to the auth form. After login the
user lands on the lessons list (or the lesson they deep-linked); after logout —
or on any 401 from an authenticated fetch — the UI drops back to the auth form.

## Code-execution safety (threat model + isolation)

User code is **hostile by assumption** and is **never imported or exec'd in the
API process**. Each submission runs in a throwaway Docker container.

| Threat | Mitigation |
|---|---|
| Infinite loop / CPU spin | `--cpus` cap **and** a host-side asyncio wall-clock kill (`SANDBOX_WALL_TIMEOUT_SECONDS`) that `docker run` cannot outlive. Verified: an infinite loop returns status `timeout`. |
| Memory exhaustion | `--memory` + `--memory-swap` equal (no swap escape). |
| Fork bomb | `--pids-limit 128`. |
| Network exfiltration / SSRF | `--network none`. Verified: sockets get `Network is unreachable`. |
| Filesystem tampering / persistence | `--read-only` root FS; only an ephemeral `noexec` tmpfs `/work` is writable; user files mounted `/code:ro`. Verified: writing `/etc` gives `Read-only file system`. |
| Privilege escalation | non-root container user (uid 10001), `--cap-drop ALL`, `--security-opt no-new-privileges`. |
| Output flooding | per-test message and captured output truncated by the runner/client. |

**Limitation (be explicit):** this is **container isolation via the host Docker
daemon**, not a hardened multi-tenant sandbox. The API host can spawn
containers, so the API process is trusted. A determined kernel-level escape is
out of scope for a single-user MVP; stronger isolation (gVisor/Kata, a separate
runner host, seccomp profiles) is a next-stage option and must be approved per
`.claude/rules/stack.md`. `--network none` + `--read-only` + `--cap-drop ALL` +
resource caps is the safest option achievable on the fixed stack today.

## Prerequisites

- Python 3.13, [uv](https://docs.astral.sh/uv/), Docker (daemon running).

## Environment variables

Copy the examples and fill them in (real `.env` files are gitignored):

```bash
cp services/api/.env.example services/api/.env
cp deploy/.env.example deploy/.env
# set a password in both; keep DATABASE_URL host/port in sync with deploy/.env
```

`services/api/.env`:

| Var | Meaning |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://coach:<pw>@localhost:5544/coach` |
| `SANDBOX_IMAGE` | tag built from `services/sandbox/Dockerfile` |
| `SANDBOX_WALL_TIMEOUT_SECONDS` | hard kill per run (e.g. `10`) |
| `SANDBOX_MEMORY_LIMIT` | e.g. `256m` |
| `SANDBOX_CPU_LIMIT` | e.g. `1.0` |
| `DOCKER_BIN` | path to docker CLI (`docker`) |
| `JWT_SECRET` | **required, no default** — HS256 signing secret for access + confirmation tokens |
| `JWT_ACCESS_TOKEN_MINUTES` | access-token lifetime, e.g. `1440` |
| `JWT_CONFIRM_TOKEN_MINUTES` | email-confirmation-token lifetime, e.g. `60` |
| `SMTP_HOST` | SMTP server host; **leave empty to log the confirmation link instead of sending** |
| `SMTP_PORT` | SMTP port, e.g. `587` |
| `SMTP_USER` / `SMTP_PASSWORD` | SMTP credentials (blank when `SMTP_HOST` is empty) |
| `SMTP_FROM` | From address, e.g. `no-reply@example.com` |
| `PUBLIC_BASE_URL` | base URL the confirmation link points at, e.g. `http://localhost:8077` |
| `OPENAI_API_KEY` | OpenAI key for the AI features (hints + lesson chat). **Leave empty to disable them** — server-side only, never sent to the browser |
| `OPENAI_MODEL` | chat model, default `gpt-4o-mini` |
| `OPENAI_FAKE` | `true` runs the LLM client in an offline canned-text mode (no network); used by tests + the UI live-server so no real tokens are spent |

### AI features (optional, OpenAI-backed)

Two auth-gated features call **our backend**, which holds the key and calls
OpenAI server-side (the key never reaches the client):

- **Exercise hints** — a Hint button on each exercise asks for an *approach*
  hint (never the full solution) in the active locale (`POST /api/exercises/{id}/hint`).
  The hidden reference solution is never sent to the model.
- **Lesson chat** — a floating widget (bottom-right) where you paste a lesson
  excerpt (+ optional question) for a more detailed explanation in your locale
  (`POST /api/chat`); it is scoped to explaining the pasted material.

**Graceful disable:** when `OPENAI_API_KEY` is empty the endpoints return
`503 "AI not configured"` and the frontend hides the hint buttons + chat widget
(driven by an `ai_enabled` flag on `/api/auth/me`). The app never crashes on a
missing key — same pattern as the SMTP log-fallback.

`deploy/.env`: `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` /
`POSTGRES_PORT` (defaults to `5544` to avoid a host Postgres on 5432).

## Run locally

```bash
make api-install   # uv sync (once, or after dependency changes)
make dev           # everything else: Postgres → migrate → sandbox image → seed → uvicorn
```

`make dev` (`dev-up`) runs these steps in order and waits for each to succeed:

1. **Postgres** via `docker compose up -d --wait` — blocks until the compose
   healthcheck passes (`pg_isready`), so migrations never race the DB.
2. **Alembic migrations** (`alembic upgrade head`). Note: the
   `auth and per-user progress` migration adds the `user` table and a non-null
   `user_id` FK to `submission`/`progress`; since those pre-auth rows had no
   owner, the migration **deletes existing `submission`/`progress` rows** (they
   are throwaway test data). Lessons/exercises/tests are untouched.
3. **Sandbox Docker image** build.
4. **Seed** the placeholder lesson (upsert-by-slug — safe to re-run).
5. **uvicorn** on `:8077` — foreground, keeping the terminal live. (Non-standard
   port to avoid clashing with other local projects; override with
   `make api-run API_PORT=xxxx`.)

Then open `http://127.0.0.1:8077/`: logged out, you see only the login/register
form. **Register** (confirm the email), **log in**, and you land on the lessons
list at `/lessons`. No lesson content is reachable until you are logged in.

**Confirming an account without SMTP:** with `SMTP_HOST` empty, the confirmation
link is logged instead of emailed. Grab it from the server output and open it:

```bash
# register
curl -s -X POST http://127.0.0.1:8077/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"correct horse battery"}'
# the uvicorn log prints: {"event":"email.confirmation_link","confirm_url":"http://localhost:8077/api/auth/confirm?token=..."}
# open that confirm_url, then log in:
curl -s -X POST http://127.0.0.1:8077/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"correct horse battery"}'   # -> {"access_token": "...", ...}
```

To stop: `Ctrl-C` (kills uvicorn), then `make dev-down` to tear down Postgres.

You can still run steps individually:

```bash
make deploy-up        # start Postgres only
make api-migrate      # alembic upgrade head
make sandbox-build    # build the sandbox Docker image
make api-seed         # load the THROWAWAY placeholder lesson
make api-run          # uvicorn on :8077 (override: API_PORT=xxxx)
make deploy-down      # stop Postgres
```

## Useful commands

| Command | Does |
|---|---|
| `make sandbox-smoke` | Run a trivial passing test through the sandbox (no API/DB). |
| `make api-test` | `pytest`. |
| `make api-lint` | `ruff check` + `ruff format --check`. |
| `make api-typecheck` | `pyright`. |
| `make api-contracts` | `lint-imports` (layer architecture check). |
| `make api-makemigration m="msg"` | autogenerate an Alembic revision. |

## What is NOT implemented (next stage)

- **Real content.** Hand `STORAGE_CONTRACT.md` to the **methodist agent** to
  author lessons/exercises/tests. The placeholder fixture is throwaway.
- **Auth hardening (next stage).** Implemented now: email+password register,
  email confirmation, Argon2 hashing, JWT bearer sessions, per-user progress.
  Deferred: **rate limiting** on register/login/submit, **refresh tokens** (only
  a single access token today; on expiry the user re-logs in), **password
  reset**, token revocation/logout-server-side (logout is client-side only),
  account deletion, and resend-confirmation.
- **Async grading / queue.** Submissions grade synchronously in-request. Heavy
  use would want a job queue (Redis) + a `PENDING → result` poll flow (the
  schema already has `PENDING` and a `GET /submissions/{id}`).
- **Hardened sandbox.** gVisor/Kata/seccomp, a dedicated runner host, image with
  extra libs, `conftest.py` support per exercise.
- **Progress analytics.** Implemented now: per-exercise progress, derived lesson
  completion, sequential unlock with 403 gating, a curriculum list with
  completed/current/locked states, a "Next lesson" flow, and a profile/cabinet
  page with an overall progress bar. Deferred: streaks, time-on-task, per-test
  history, and richer dashboards.
- **Allure / Playwright UI tests & httpx API integration tests.** Owned by the
  `qa` agent. Current tests are unit-level only.
- **Rate limiting / abuse controls** on the submit endpoint.

## Open questions and assumptions

**Assumptions made:**
1. Email+password auth with email confirmation and JWT bearer sessions
   (owner-approved). Effectively single-owner, but accounts are no longer
   anonymous; progress is per account.
2. The API host may talk to the Docker daemon (the API process is trusted; only
   *user code* is untrusted). Acceptable for a single-user personal platform.
3. Synchronous grading is fine at single-user scale (one container per request).
4. Each exercise's tests are independent files; no shared `conftest.py` yet.
5. Postgres on `5544` locally to dodge a common 5432 clash — adjust freely.

**Open questions for the owner:**
1. Should hidden-test *failures* reveal the assertion message, or only "a hidden
   test failed"? (Currently the message is included.)
2. Wall-clock/memory defaults (10s / 256m) — tune for the kinds of exercises the
   methodist will write (e.g. generator/perf tasks may need more)?
3. Do exercises ever need third-party libraries inside the sandbox? If yes, the
   sandbox image and ingest format need a dependency field (next stage).
4. Is a curriculum/lesson-list page wanted in the next stage, or is direct
   `?lesson=<slug>` navigation enough for now?
5. Should re-ingesting a lesson preserve historical submissions/progress? (Today
   ingest replaces the lesson and cascades — progress rows referencing deleted
   exercises are removed.)
```
