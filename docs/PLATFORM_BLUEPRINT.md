# Platform Blueprint — a learning-platform factory

> Build log **and** reusable blueprint for this repository. It explains both how
> `python-coach` was constructed and how the same scheme builds *any* other
> learning platform by swapping the source books in `sources/`.
>
> This document is descriptive — it changes no code and ships nothing.

---

## 1. What this is

`python-coach` is a personal, interactive web platform for learning advanced
Python with a test-automation (AQA) slant: a learner reads a lesson, writes
Python in an in-browser editor, submits it, the server grades the code by running
the exercise's **pytest** tests in an **isolated Docker sandbox**, and the
structured result plus per-user progress are stored and shown. The
end-to-end shape and entities are fixed in [`CONTEXT.md`](../CONTEXT.md).

**The factory thesis.** The interesting claim of this repo is not the Python
course — it is that *the platform is a factory for learning platforms*. The
infrastructure (auth, the Docker grading sandbox, the bilingual content model,
sequential unlock/completion gating, the profile/progress page, i18n, the layered
FastAPI service) is **subject-agnostic**. The *only* subject-specific input is the
books in `sources/`. A `methodist` agent turns those books into
[`CURRICULUM.md`](../CURRICULUM.md) (a topic map) plus bilingual lesson fixtures
in `fixtures/`. To retarget the platform to a different subject you swap the
books, restate the goal/target skill in `CONTEXT.md`, and regenerate the content —
the infra is reused unchanged (with one Python-specific caveat about the grader,
called out in §7).

This separation is enforced socially (by agent role boundaries) and structurally
(by the storage contract and the import-linter layering), not just by convention.

---

## 2. The agent suite (the factory)

Five agents in `.claude/agents/` divide the work so that *content* and
*infrastructure* never bleed into each other. The architect builds the machine and
the contract; the methodist feeds it; coder/reviewer/qa are generic workers driven
entirely by `.claude/rules`.

| Agent | Role / what it owns | When it runs | Must NOT do |
|---|---|---|---|
| **python-platform-architect** (`opus`) | Stands up the working baseline: data model, DB schema + migrations, layered FastAPI API, the Docker pytest sandbox + threat model, the lesson-page frontend, and the **storage contract**. Authors `CONTEXT.md`, `STORAGE_CONTRACT.md`, `README.md`. | Once, at the start (the vertical slice), and for later infra features. | **Never authors lesson content.** Any lesson data it creates is throwaway synthetic fixture (`placeholder_lesson.json`) to prove the pipeline. It does not produce a curriculum or copy book text. |
| **methodist** (`opus`) | Authors content *against the frozen contract*: builds/owns `CURRICULUM.md`, writes bilingual EN+RU lessons + exercises + their pytest tests, validates each solution against its tests before emitting. | After the infra exists, repeatedly — one call ≈ one complete lesson (organised into waves). | **Never changes schema, contract, stack, or architecture.** Never copies text from the paid books (reference-only); flags contract gaps but still emits in the current format. |
| **coder** (`sonnet`) | Generic implementation worker: writes/edits code to spec, mirrors surrounding style, runs lint/typecheck/tests. | Whenever a feature or fix needs writing. | Nothing subject-specific — it has no product vision; it obeys `.claude/rules/*`. Flags (but follows) any rule/user conflict. |
| **code-reviewer** (`opus`) | Reviews a diff/PR for correctness + rule/layering compliance; also triages existing review comments (validate → apply/reject/clarify → always reply). | Before merge / on PRs. | Read-only for code — proposes fixes and hands off to `coder`; does not edit product files itself. |
| **qa** (`opus`) | Writes/maintains API tests (pytest + httpx) and UI tests (Playwright + pytest, optional Allure). The test is the oracle of the spec. | After features land; for regression coverage. | Never edits product code to make a test pass (one exception: adding a `data-testid`). Genuine product bugs go to `docs/bugs/` + an `xfail`/`skip`. |

**The cut that matters.** The architect and methodist are *project-specific* (they
embody this product's vision and this subject's content). coder/reviewer/qa are
*generic*: their prompts contain no Python-course knowledge — they only know how to
read `.claude/rules/*` and execute. That is what makes the bottom three reusable
across any repo on the same stack.

**Deferred plugin extraction.** `.claude/PLUGIN_EXTRACTION_PLAN.md` records the
plan (status: *deferred — do not extract yet*) to promote coder/reviewer/qa + the
generic rules (`python`, `all-languages`, `docker`, `makefile`, `dotenv`) + the QA
references into a versioned **Claude Code plugin**, while keeping
`python-platform-architect`, `methodist`, and the project-contract rules
(`stack`, `api-layers`) project-local. The mechanism relies on Claude Code's
override precedence (project `.claude/agents/` wins over plugin agents) and the
fact that a globally-installed agent reads the *current* project's
`.claude/rules/`. Known friction (no `${PLUGIN_ROOT}` for agents; the QA refs must
become a bundled skill) is documented there. The revisit trigger: after one
successful architect run + at least one methodist lesson + one qa pass with stable
prompts — which has now happened, so the plan is ready to action when desired.

---

## 3. The rules layer (how generic agents produce consistent code)

`.claude/rules/*.md` is the shared contract every code-touching agent loads first.
Each file's `paths:` frontmatter scopes it to matching files. This is the
mechanism by which *generic* workers produce *consistent* code without
subject knowledge.

| Rule file | Scope (`paths:`) | What it enforces / why it matters |
|---|---|---|
| `stack.md` | `**/pyproject.toml` | The single source of truth for technologies (Python 3.13, uv, FastAPI, Pydantic v2, SQLModel/SQLAlchemy 2.0 async, asyncpg, Alembic, uvicorn, structlog, Docker sandbox, pytest/httpx/Playwright, argon2-cffi + PyJWT, stdlib smtplib). Adding/replacing anything requires explicit owner approval — prevents tooling drift. |
| `api-layers.md` | `services/api/**/*.py` | Backend layering: `transport → controllers → storage/clients`, one direction only; controllers never import `fastapi`; one `Storage` class composed of per-domain mixins (no `*Repository`); no `Protocol`/`ABC` while there is one implementation. Enforced at CI by **import-linter**. |
| `python.md` | `**/*.py` | uv-only (never `pip`); all config in `pyproject.toml` (no `*.ini`); full type hints, built-in generics, parameterised `dict`; dataclasses over tuples for multi-returns; absolute imports; PEP-420 (no stray `__init__.py`); `pydantic-settings` read-once-and-freeze; early returns; docstrings that say *why*. |
| `all-languages.md` | `**/*.{js,ts,tsx,go,py}` | No abstraction until two implementations exist; **config values are required, no in-code defaults** (fail fast on missing env); English-only identifiers/commits; no `print` in services; ±500-line file cap. |
| `pyproject.md` | `**/pyproject.toml` | Hatchling build backend; runtime vs dev deps split (PEP 735 `[dependency-groups]`); pin sentinels; `requires-python = ">=3.13"`; tool config inside `pyproject.toml`. |
| `dotenv.md` | `**/.env*` | `.env*` lives next to its consumer (`services/api/.env`, `deploy/.env`); commit only `.env.example` with placeholders; no real secrets; `KEY=VALUE` format. |
| `docker.md` | `**/Dockerfile*` | Pin base images (never `:latest`); multi-stage; least-to-most-volatile layer order; non-root user; apt hygiene; explicit `WORKDIR`. |
| `makefile.md` | `**/Makefile` | Root Makefile is a pure dispatcher; domain-prefixed targets (`api-*`, `deploy-*`, `dev-*`); soft `-include .env`; resolve paths via `git rev-parse --show-toplevel` (no relative `cd`). |

`.claude/references/qa/` holds *generic* Playwright/pytest/Allure best-practice
references (flakiness checklist, selectors, async patterns, POM patterns, Allure,
performance, a pitfalls journal) that `qa` and `code-reviewer` consult on demand —
deliberately separate from the rules so they can travel into the future plugin.

---

## 4. Architecture (the subject-agnostic infra)

All paths below exist in the repo. The service is a uv-workspace member at
`services/api/`.

### Layered FastAPI service (`services/api/src/python_coach/`)

Layering is enforced by import-linter (`make api-contracts`), matching
`api-layers.md`:

- **`transport/`** — FastAPI routers + DTOs + `deps.py` (the single stitching
  point that builds `Storage`, injects clients, and resolves the current user from
  the JWT). Routes under `transport/rest/{auth,lessons,submissions,progress,profile}/routes.py`.
- **`controllers/`** — use-cases taking unpacked primitives, never importing
  `fastapi`: `auth.py` + `security.py` (register/confirm/login, Argon2 hashing, JWT
  helpers), `lessons.py` (the completion/unlock fold — the gate), `profile.py`
  (reuses that fold), `submissions.py`, `progress.py`.
- **`storage/`** — one `Storage` class (`storage/storage.py`) composed of per-domain
  mixins (`_lessons.py`, `_submissions.py`, `_progress.py`, `_users.py`); SQLModel
  tables in `storage/models/{lesson,submission,user}.py` double as domain models;
  `db.py` owns the async session.
- **`clients/`** — external clients: `sandbox.py` (`SandboxClient`, the Docker
  runner), `email.py` (`EmailClient`, stdlib smtplib via `asyncio.to_thread`),
  `sandbox_result.py` (the `TestResult`/`TestRunResult` dataclasses, *not* DB
  tables — serialized into `Submission.result` JSONB).
- `app.py` (ASGI entrypoint, routers, static page, SPA catch-all, structlog),
  `settings.py` (frozen `pydantic-settings`), `seed.py` (the ingest CLI),
  `migrations/` (Alembic, config in `pyproject.toml`, no `alembic.ini`).

### Docker-isolated pytest sandbox (`services/sandbox/`)

User code is **hostile by assumption** and never imported or `exec`'d in the API
process. Each submission runs in a throwaway container.

- `Dockerfile` — pinned `python:3.13.1-slim-bookworm`, multi-stage, non-root user
  `sandbox` (uid 10001). The image installs **only `pytest==8.3.4`** into a venv —
  by design nothing else is importable inside the sandbox.
- `runner/run_tests.py` — runs *inside* the container: copies the read-only `/code`
  mount into the writable `noexec` tmpfs `/work`, runs pytest with a small
  collector plugin, and prints a single JSON result payload between markers on
  stdout (stdout *is* the transport). 0 collected tests → runner error, not a pass.
- `SandboxClient` launches `docker run` with `--network none`, `--read-only`,
  `--cap-drop ALL`, `--security-opt no-new-privileges`, `--memory`/`--memory-swap`
  equal, `--cpus`, `--pids-limit`, plus a **host-side asyncio wall-clock kill** that
  `docker run` cannot outlive. The threat-model table (infinite loop, memory
  exhaustion, fork bomb, network exfiltration, FS tampering, privilege escalation,
  output flooding) is in [`README.md`](../README.md) "Code-execution safety".
  Explicit limitation: this is container isolation via the host Docker daemon, not
  a hardened multi-tenant sandbox; gVisor/Kata/seccomp is a stack-approval-gated
  next stage.

### Data model, auth, and progression

- **SQLModel/Alembic.** `lesson` 1—∞ `exercise` 1—∞ `exercise_test`; `lesson` and
  `exercise` each carry per-locale translation tables (`lesson_translation`,
  `exercise_translation`). `user` 1—∞ `submission`/`progress`, both with a
  `user_id` FK; `progress` unique per `(user_id, exercise_id)`. `submission.result`
  is JSONB. Three migrations: `…_initial_schema`, `…_bilingual_prose_and_solution_code`,
  `…_auth_and_per_user_progress`.
- **JWT auth + email confirmation.** Email + password (Argon2id via `argon2-cffi`);
  account starts unconfirmed; a signed purpose-tagged confirmation JWT is emailed
  (or **logged via structlog** when SMTP is unconfigured, so local dev needs no SMTP
  creds); login issues an HS256 JWT bearer access token. **Everything
  content-related requires the token** (401 without it); the only public endpoints
  are the auth routes.
- **Bilingual {en, ru} content model.** All learner-facing *prose* (lesson
  `title`/`body_md`, exercise `title`/`statement_md`) exists in both locales;
  **code-bearing fields are language-neutral and single-valued** (`starter_code`,
  `solution_code`, `solution_module`, each test's `filename`/`content`/`is_hidden`).
  The API returns both locales in one payload; the frontend switches instantly
  client-side (`static/i18n.js`); missing-locale prose falls back rather than erroring.
- **Sequential unlock + derived completion.** Completion is *derived* (no stored
  flag): a lesson is complete when it has exercises and the user has a solved
  `Progress` row for each. Over published lessons ordered by `position`, a lesson is
  unlocked iff it is first or the previous published lesson is complete; a locked
  lesson returns **403** (no content served) and submissions to it return 403. The
  gate is server-side; `controllers/lessons.py` computes both flags in one fold
  reused by the list, single read, submission gate, and profile (no N+1).
- **Profile / progress page.** `GET /api/profile` (route `/profile`) returns the
  user's email, an ordered per-lesson status list (solved/total, completed,
  unlocked), and totals. `controllers/profile.py` reuses the lessons fold.
- **SPA frontend + i18n.** Single-page UI in `services/api/static/`:
  `index.html`, `app.js`, `auth.js`, `exercise.js`, `profile.js`, `i18n.js`,
  `app.css`, using CDN CodeMirror 5 + `marked` (no build step). A backend SPA
  catch-all serves the shell for client-side routes (`/lessons`, `/profile`); the
  JS gates every view behind the token and stashes deep links for post-login return.

---

## 5. The content seam (the only subject-specific part)

Everything in §4 is subject-agnostic. The single seam where "Python" enters the
system is the path **`sources/` → methodist → `CURRICULUM.md` → `fixtures/lesson_*.json`**.

1. **`sources/` (the books).** Three PDFs: *Intermediate Python* (Yasoob, free
   — the rewordable backbone), *Fluent Python* (Ramalho) and *Python Testing with
   pytest* (Okken) — both **reference-only**. The methodist may use the free book
   as a backbone (still reworded) but is **forbidden** to copy text, examples, or
   exposition structure from the paid books; topic coverage only. `CURRICULUM.md`
   tags each topic with its source legend (`Y`/`R`/`O`/`orig`) precisely to keep
   this auditable.
2. **`CURRICULUM.md` (topic map, owned by methodist).** Structure only — no copied
   text. 23 topics across 7 tracks, ordered basic → advanced with an AQA slant,
   each row giving the lesson `slug`, `position`, source tag, status, and the AQA
   connection. This is the build order for content.
3. **`fixtures/lesson_*.json` (the ingest format).** One JSON file = one lesson,
   matching [`STORAGE_CONTRACT.md`](../STORAGE_CONTRACT.md). Verified shape (e.g.
   `lesson_decorators_basics.json`): top-level `slug`, `title` (`{en, ru}`),
   `body_md` (`{en, ru}`), `position`, `is_published`, `exercises[]`; each exercise
   has `slug`, `title`/`statement_md` (`{en, ru}`), `starter_code`, `solution_code`
   (hidden), `solution_module`, `position`, `tests[]`; each test has `filename`,
   `content` (full pytest source), `is_hidden`, `position`.

**The grading model.** An exercise's tests `import` the learner's submission as a
module named by `solution_module` (default `solution`) — i.e. tests write
`from solution import ...`. The methodist authors a **hidden reference
`solution_code`** and a **predefined pytest** suite, and validates by running the
tests against the solution (must pass) and against a wrong/empty solution (must
fail) before emitting. Two fields are stored but **never sent to the frontend**
(anti-cheat): `solution_code` (always) and a test's `content` when `is_hidden=true`.

**Ingest.** `seed.py` upserts by lesson `slug` (re-running replaces the lesson and
its exercises/tests). A prose field may be a `{en, ru}` object or a bare string
(filled across locales as a legacy safety net); `solution_code` accepts the legacy
`_solution_code` alias. `make api-seed-all` ingests every fixture.

The 23 lessons were authored in four "waves" (see §6); `CURRICULUM.md` records all
23 as done.

---

## 6. Build log / phase sequence

The git history *is* the build log; commit subjects are detailed. Reconstructable
journey (oldest → newest):

| Phase | Commits (subject) |
|---|---|
| **0. Factory setup** | `Add .claude agent suite, rules, and QA references`; `Document deferred plugin-extraction plan for reusable agents`. |
| **1. Vertical slice (architect)** | `Add vertical-slice MVP skeleton (DB + API + sandbox + lesson page)` — layered FastAPI, Docker sandbox, SQLModel + Alembic, static lesson page, `CONTEXT.md`/`STORAGE_CONTRACT.md`/`README.md`, throwaway placeholder fixture. |
| **2. First content + curriculum** | `Add curriculum map and first real lesson (decorators basics)`. |
| **3. QA + first product bugs** | `Add QA test suite (API + UI) and fix the two product bugs it surfaced` (→ `docs/bugs/0001`, `0002`). |
| **4. Local DX** | `Add make dev one-command local environment startup`; `Move API to non-standard port 8077…`; `Unify the sandbox image into the deploy compose stack`. |
| **5. i18n / bilingual content model** | `Add bilingual (EN/RU) content model, language switcher, and solution_code`; `methodist: mandate bilingual EN/RU prose and solution_code`; `Add bilingual decorators lessons…`. |
| **6. Lesson list** | `Add bilingual lesson-list page and GET /api/lessons`; `Add bilingual functools-toolkit lesson`; `Add QA coverage for the language switcher and list endpoint/page`. |
| **7. Content waves 1–4** | `…wave 1: Tracks 1-2`; `…wave 2: Tracks 3-4`; `…wave 3: Tracks 4-6`; `…wave 4: Track 6-7 capstone — curriculum complete` (all 23 lessons, bilingual). |
| **8. Auth** | `Add email+password authentication with email confirmation and per-user progress` (Argon2, JWT, `user` table + per-user `submission`/`progress`). |
| **9. Content gating** | `Fix auth-modal login-form visibility…` (→ `docs/bugs/0003`); `Gate all content behind auth: login landing, lessons on /lessons, deep-link redirect`. |
| **10. Progression / profile** | `Add lesson progression (completion, sequential unlock, next-lesson, profile) + stop tests emailing` (→ `docs/bugs/0004`). |
| **11. Fixes** | `Render all exercises of a lesson (not just the first)` (→ `docs/bugs/0005`, a progression-blocking UI bug). |

Note the rhythm: the architect builds the machine once (phase 1), then content
(methodist) and infra features (architect/coder) interleave, each backed by qa and
recorded bugs.

---

## 7. How to build a NEW learning platform with this scheme

The playbook to retarget the factory to a different subject:

1. **Drop the new subject's books into `sources/`.** Replace the three PDFs. Note
   each book's license so the methodist knows which are rewordable backbone vs
   reference-only.
2. **Restate the goal in `CONTEXT.md`.** Update the *Goal*, *User profile*, and
   *Target skill* sections to the new subject. The domain-entity table, data flow,
   auth model, bilingual model, and progression model stay as-is — they are
   infra, not content.
3. **Reset and regenerate `CURRICULUM.md`, then run the methodist per topic.**
   Build a fresh topic map from the new books (structure only, respecting
   copyright + the source legend), then invoke the `methodist` agent in waves —
   one lesson per call — to emit bilingual `fixtures/lesson_*.json`. Each lesson
   self-validates (solution passes its tests, a wrong solution fails) before
   emitting. Delete the old fixtures.
4. **Bring it up.** `make api-install` once, then `make dev` (Postgres → migrate →
   sandbox build → `api-seed-all` → uvicorn on `:8077`). Register, confirm
   (the link is logged when SMTP is unset), log in.
5. **The infra needs no change** — *if the taught subject is still Python.* Auth,
   the sandbox, progression, profile, and i18n are all subject-agnostic and reused
   verbatim.

### Honest reusability assessment — what is reusable as-is vs what needs adaptation

**Reused unchanged for any subject:** the layered API, JWT auth + email
confirmation, per-user progress, sequential unlock/derived completion, the
profile page, the SPA + i18n, the bilingual content model, the ingest format and
`seed.py`, the storage contract, and the entire agent/rules machinery (the bottom
three workers are already generic).

**The main retarget caveat — the grader is Python-specific.** Two assumptions bake
"Python" into the infra:

- **The sandbox image** (`services/sandbox/Dockerfile`) installs the Python
  toolchain + `pytest`. A non-Python subject (JS, SQL, Go, …) needs a different
  image with that language's runtime and grader.
- **"Tests are pytest."** `runner/run_tests.py` runs pytest and parses its
  per-test outcomes into the JSON result payload; `solution_module` and
  `from solution import …` assume a Python import model. A different grader (Jest,
  `go test`, a SQL harness) means rewriting `run_tests.py`'s collection/parsing and
  rethinking how the learner's submission is named/loaded — though the *result
  contract* (`passed`, per-test name/outcome/message JSON) and `SandboxClient`'s
  isolation flags can stay.

So for a *Python* subject the factory is a pure book-swap. For a *non-Python*
subject, everything except the sandbox image and the grader/runner is reusable;
those two pieces are the language-specific surface to re-implement (a
stack-approval-gated change per `stack.md`). The content seam (§5) is unchanged in
either case — `STORAGE_CONTRACT.md` already treats `content`/`filename` as opaque
test sources.

---

## 8. Known limitations / next stage

Pulled from `README.md` "What is NOT implemented", `docs/bugs/`, and the recorded
open questions:

- **Auth hardening (deferred):** rate limiting on register/login/submit, **refresh
  tokens** (only a single access token today; re-login on expiry), password reset,
  server-side token revocation/logout (logout is client-side), account deletion,
  resend-confirmation.
- **Async grading / queue:** submissions grade synchronously in-request; heavy use
  would want a Redis job queue + a `PENDING → poll` flow (the schema already has
  `PENDING` and `GET /submissions/{id}`).
- **Hardened sandbox:** gVisor/Kata/seccomp, a dedicated runner host, per-exercise
  `conftest.py`, and a sandbox image with extra libraries (today only `pytest` is
  importable, so a lesson needing a third-party lib is a next-stage image change).
- **More locales:** the content model is bilingual {en, ru}; adding locales is a
  content + i18n-table extension.
- **Non-Python graders:** the §7 caveat — the sandbox image and pytest-runner are
  the language-specific pieces.
- **Richer analytics:** streaks, time-on-task, per-test history, dashboards.
- **Full e2e/Allure coverage:** present tests are unit + targeted API/UI; broader
  Allure/Playwright/httpx integration is owned by `qa`.
- **Resolved bugs (`docs/bugs/`), all FIXED:** `0001` sandbox timeout proc-kill
  race; `0002` static-dir path off-by-one (frontend unreachable); `0003` auth-modal
  login-form not hidden; `0004` test suite sent real confirmation emails; `0005`
  lesson rendered only the first exercise (progression-blocking).
- **Open questions for the owner** (from `README.md` / `CONTEXT.md`): whether hidden-
  test *failures* should reveal the assertion message; wall-clock/memory defaults
  (10s / 256m) tuning; whether exercises ever need third-party libs in the sandbox;
  whether re-ingesting a lesson should preserve historical submissions/progress.
