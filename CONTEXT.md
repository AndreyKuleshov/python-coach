# CONTEXT — python-coach

> Stage-1 context document produced by the `python-platform-architect` agent.
> Scope: infrastructure + storage contract for a personal Python learning
> platform. **Content (lessons/exercises) is authored separately by the
> methodist agent** — everything here is infrastructure plus throwaway fixtures.

## Goal

A personal, interactive web platform for learning **advanced Python with a
test-automation (AQA) slant**. The learner reads a lesson, writes Python in an
in-browser editor, submits it, the server runs the exercise's **pytest** tests
against the code in an **isolated sandbox**, and the structured result + progress
are shown and stored.

## User profile

- **Registered accounts.** Login is by **email + password**; the email must be
  **confirmed** before login. Progress and submissions are tracked **per
  account**. The platform is still effectively single-owner, but it is no longer
  anonymous: **no content is reachable without logging in** — lessons, exercises,
  submissions and progress all require a valid token.
- Intermediate developer learning AQA: decorators, generators, context managers,
  function arguments, OOP/dunder methods — all leaning toward pytest and test
  automation.

## Product requirement: authentication + per-user progress

- **Register** with email + password (Argon2id hash via `argon2-cffi`). The
  account starts **unconfirmed**; a signed confirmation link is emailed (real
  SMTP when configured, otherwise the link is **logged** via structlog so it is
  usable locally without SMTP creds).
- **Confirm** by following the link (a short-lived purpose-tagged JWT — no token
  table). Confirmation flips `is_email_confirmed`.
- **Login** verifies the Argon2 hash; an unconfirmed account is rejected (403),
  a confirmed one receives a **JWT bearer access token** (HS256, `JWT_SECRET`,
  with an expiry).
- **Protected (everything content-related):** the lesson endpoints
  (`GET /api/lessons`, `GET /api/lessons/{slug}`), `POST /api/submissions`, the
  progress endpoints, and `GET /api/profile` all require the bearer token. Lesson
  reads are now **keyed to the user** too: they derive completion/unlock per
  account and a **locked** lesson is refused with **403** (the list still lists
  every published lesson with its `is_completed`/`is_unlocked` flags so the UI
  can render locked rows). Submissions/progress/profile are keyed to the current
  user. A request without/with an invalid token → **401**.
- **Public (the only unauthenticated endpoints):** the auth routes —
  `POST /api/auth/register`, `GET /api/auth/confirm`, `POST /api/auth/login`
  (`GET /api/auth/me` resolves the current user from the token).

### Access model on the frontend

- A **logged-out visitor sees only the inline auth form** (login/register) on
  every route — never the lesson list, never a lesson. `/` is the landing: it
  shows the auth form when logged out and redirects to the lessons list when
  authenticated.
- The **lessons list is its own authenticated view at `/lessons`** (distinct
  from the landing). A backend SPA catch-all serves the same shell for `/lessons`
  so the JS router can resolve it; the JS gates the view behind a token.
- A **logged-out deep link** (`/lessons` or `/?lesson=<slug>`) lands on the auth
  form, not the content; the requested path is stashed so a successful login
  returns the user to it (else to `/lessons`). **After logout** — or if any
  authenticated fetch returns 401 — the UI drops back to the auth form.

## Product requirement: progression (completion + sequential unlock + profile)

Learning is a guided sequence, not a free-for-all. Three product facts, all
enforced **server-side** (the API is the real gate; the frontend mirrors it):

- **Lesson completion** is *derived*, not stored: a lesson is **completed** by a
  user when it has at least one exercise **and** every exercise in it has a
  solved per-(user, exercise) `Progress` row. There is no redundant
  `is_completed` column — it is computed from existing progress.
- **Sequential unlock** over PUBLISHED lessons ordered by `position`: a lesson is
  **unlocked** iff it is the first published lesson **or** the immediately
  preceding published lesson is completed by the user. A **locked** lesson is not
  accessible — `GET /api/lessons/{slug}` returns **403** and a submission to one
  of its exercises returns **403** (you cannot progress a locked lesson).
- **Next lesson** = the next published lesson by `position`. The lesson read
  exposes `next_slug` (null on the last lesson) so the UI can offer a "Next
  lesson →" button once the current lesson is completed.
- **Personal profile / cabinet** (`GET /api/profile`, route `/profile`): the
  user's email + an ordered list of all published lessons each with
  solved/total exercise counts and `is_completed` / `is_unlocked`, plus totals
  (`lessons_completed` / `lessons_total`). Scoped to the bearer-token user — no
  cross-user data.

Completion + unlock are computed efficiently: two aggregate queries
(`exercise_counts_by_lesson`) yield total and solved-per-lesson counts in one
pass, and a single fold over the position-ordered published lessons derives both
flags (no N+1). The list (`GET /api/lessons`), the single-lesson read, the
submission gate, and the profile all reuse this one fold.

## Target skill: AQA

The content focus (authored later) is test automation. The platform itself uses
pytest as the *grading* mechanism, which doubles as exposure to the tool the
learner is studying: an exercise's checks are real pytest tests.

## Product requirement: bilingual content (en + ru)

All learner-facing **prose** exists in both English and Russian: lesson `title`
and `body_md`, exercise `title` and `statement_md`. **Code-bearing fields are
language-neutral and single-valued**: `starter_code`, `solution_code`,
`solution_module`, and each test's `filename`/`content`/`is_hidden` (code is
code; pytest names and assertion messages are not translated). The lesson API
returns **both locales in one payload**; the frontend switches language
instantly client-side (no reload, no re-fetch). Default language follows the
browser (`navigator.language`, fallback English); a manual choice is persisted
in `localStorage` and wins on later visits. Missing-locale prose falls back to
the other locale rather than erroring.

## Product requirement: AI assistance (optional, OpenAI-backed)

Two auth-gated helpers, generated on the fly by OpenAI. The key
(`OPENAI_API_KEY`) lives **only on the server** (`services/api/.env`): the
browser calls our backend, the backend calls OpenAI, the key is never sent to
the client.

- **Exercise hints** — each exercise has a Hint button that returns a short hint
  about the *approach* (explicitly **not** the full solution), in the interface
  language (en/ru). Only the public statement + starter code are sent to the
  model; the hidden `solution_code` is never forwarded, so it cannot leak.
  Hints obey the same lesson-lock gate as submissions (no hints for locked
  content).
- **Lesson chat** — a floating widget where the learner pastes a lesson excerpt
  (+ optional question) for a more detailed explanation in their locale. The
  assistant is scoped to explaining the pasted material and declines off-topic
  requests. Excerpt/question lengths are capped to bound token cost.

Default model `gpt-4o-mini` (override via `OPENAI_MODEL`). When the key is empty
the features are **gracefully disabled**: the endpoints return `503` and the
frontend hides the hint buttons + chat widget (driven by an `ai_enabled` flag on
`/api/auth/me`) — the app never crashes, mirroring the SMTP log-fallback.

## Domain entities

| Entity | Meaning | Key relationships |
|---|---|---|
| **Lesson** | A lesson (bilingual title + markdown body) + ordered exercises. | 1 Lesson → many Exercise; 1 Lesson → many LessonTranslation |
| **LessonTranslation** | Per-locale lesson prose (`en`/`ru`): title + body_md. | belongs to Lesson, unique per `(lesson, locale)` |
| **Exercise** | One coding task: bilingual statement/title, language-neutral starter code, hidden reference `solution_code`, the module name the user's code is saved as. | 1 Exercise → many ExerciseTest; 1 Exercise → many ExerciseTranslation |
| **ExerciseTranslation** | Per-locale exercise prose (`en`/`ru`): title + statement_md. | belongs to Exercise, unique per `(exercise, locale)` |
| **ExerciseTest** | One pytest test file for an exercise (visible or hidden). | belongs to Exercise |
| **User** | A registered account: email (unique, lower-cased) + Argon2 hash + email-confirmed flag. | 1 User → many Submission / Progress |
| **Submission** | One graded attempt by one user: the submitted code + the structured pytest verdict (JSONB). | belongs to User + Exercise |
| **Progress** | Per-(user, exercise) roll-up: solved flag, attempt count, last submission, solved-at. | one row per `(user, exercise)` |

`TestResult` / `TestRunResult` are **not** DB tables — they are the structured
result dataclasses (`clients/sandbox_result.py`) serialized into
`Submission.result` (JSONB). This keeps per-test detail queryable without a
separate table while the schema is young.

## Data flow (open lesson → save progress)

```
Browser (static lesson page, CodeMirror editor)
  │  (auth) POST /api/auth/register {email,password}
  │     └─ unconfirmed User + signed confirm token → email (or logged link)
  │  GET  /api/auth/confirm?token=...  → is_email_confirmed = true
  │  POST /api/auth/login {email,password} → JWT bearer access token (localStorage)
  │
  │  GET /api/lessons  /  GET /api/lessons/{slug}  + Authorization: Bearer <jwt>
  │     (authenticated-only — 401 without a valid token; no content leaks)
  ▼
transport/deps.get_current_user → resolves/validates the bearer token (401 if absent/invalid)
  ▼
transport/rest/lessons → controllers/lessons.get_lesson → storage (LessonsMixin)
  │  renders markdown + exercises (test sources NOT sent)
  │
  │  user writes code, clicks "Check"
  │  POST /api/submissions {exercise_id, code}  + Authorization: Bearer <jwt>
  ▼
transport/deps.get_current_user → resolves User from the bearer token (401 if absent/invalid)
  ▼
transport/rest/submissions → controllers/submissions.submit_solution
  ├─ storage.create_pending_submission()         (PENDING row)
  ├─ clients/sandbox.SandboxClient.run(code, tests)
  │     └─ docker run (no network, read-only FS, CPU/mem/pids caps, wall-clock kill)
  │           └─ in-container run_tests.py → pytest → JSON result on stdout
  ├─ storage.finalize_submission()               (status + JSONB result, user_id)
  └─ storage.record_attempt(user_id, ...)        (upsert per-user Progress)
  ▼
structured SubmissionDTO → results panel
  │  GET /api/progress/{exercise_id}  + Authorization: Bearer <jwt>
  ▼
progress badge updates
```

## Fixed stack (per `.claude/rules/stack.md`) — followed, no substitutions

Python 3.13 · uv (workspace) · FastAPI · Pydantic v2 + pydantic-settings ·
SQLModel on SQLAlchemy 2.0 async · asyncpg · Alembic · uvicorn · structlog ·
Docker sandbox · pytest (+ httpx for API tests) · **argon2-cffi** + **PyJWT**
for auth (owner-approved, recorded in `stack.md`) · stdlib smtplib for email.
import-linter enforces the `api-layers.md` direction.

## Design choices left to the architect (recorded)

- **Frontend editor:** a single static HTML page using **CodeMirror 5** (CDN, no
  build step) + **marked** for markdown. Rationale: minimal, dependency-free,
  matches "thin vertical slice"; can be swapped for Monaco/a bundler later.
- **Sandbox mechanics:** one **Docker container per submission** via the host
  `docker` CLI from `SandboxClient`. Files are staged in a host temp dir mounted
  **read-only** at `/code`; the in-container runner copies them to a `noexec`
  tmpfs `/work` before running pytest. Isolation flags: `--network none`,
  `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`,
  `--memory`/`--memory-swap`, `--cpus`, `--pids-limit`, plus a **host-side
  asyncio wall-clock kill**. See README "Threat model".

## Open questions / assumptions

See README → "Open questions and assumptions".
