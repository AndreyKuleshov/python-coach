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

- **Single user** (the owner). No multi-tenancy, no auth in the MVP.
- Intermediate developer learning AQA: decorators, generators, context managers,
  function arguments, OOP/dunder methods — all leaning toward pytest and test
  automation.

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

## Domain entities

| Entity | Meaning | Key relationships |
|---|---|---|
| **Lesson** | A lesson (bilingual title + markdown body) + ordered exercises. | 1 Lesson → many Exercise; 1 Lesson → many LessonTranslation |
| **LessonTranslation** | Per-locale lesson prose (`en`/`ru`): title + body_md. | belongs to Lesson, unique per `(lesson, locale)` |
| **Exercise** | One coding task: bilingual statement/title, language-neutral starter code, hidden reference `solution_code`, the module name the user's code is saved as. | 1 Exercise → many ExerciseTest; 1 Exercise → many ExerciseTranslation |
| **ExerciseTranslation** | Per-locale exercise prose (`en`/`ru`): title + statement_md. | belongs to Exercise, unique per `(exercise, locale)` |
| **ExerciseTest** | One pytest test file for an exercise (visible or hidden). | belongs to Exercise |
| **Submission** | One graded attempt: the submitted code + the structured pytest verdict (JSONB). | belongs to Exercise |
| **Progress** | Per-exercise roll-up: solved flag, attempt count, last submission, solved-at. | one row per Exercise |

`TestResult` / `TestRunResult` are **not** DB tables — they are the structured
result dataclasses (`clients/sandbox_result.py`) serialized into
`Submission.result` (JSONB). This keeps per-test detail queryable without a
separate table while the schema is young.

## Data flow (open lesson → save progress)

```
Browser (static lesson page, CodeMirror editor)
  │  GET /api/lessons/{slug}
  ▼
transport/rest/lessons → controllers/lessons.get_lesson → storage (LessonsMixin)
  │  renders markdown + exercises (test sources NOT sent)
  │
  │  user writes code, clicks "Check"
  │  POST /api/submissions {exercise_id, code}
  ▼
transport/rest/submissions → controllers/submissions.submit_solution
  ├─ storage.create_pending_submission()         (PENDING row)
  ├─ clients/sandbox.SandboxClient.run(code, tests)
  │     └─ docker run (no network, read-only FS, CPU/mem/pids caps, wall-clock kill)
  │           └─ in-container run_tests.py → pytest → JSON result on stdout
  ├─ storage.finalize_submission()               (status + JSONB result)
  └─ storage.record_attempt()                    (upsert Progress)
  ▼
structured SubmissionDTO → results panel
  │  GET /api/progress/{exercise_id}
  ▼
progress badge updates
```

## Fixed stack (per `.claude/rules/stack.md`) — followed, no substitutions

Python 3.13 · uv (workspace) · FastAPI · Pydantic v2 + pydantic-settings ·
SQLModel on SQLAlchemy 2.0 async · asyncpg · Alembic · uvicorn · structlog ·
Docker sandbox · pytest (+ httpx for API tests). import-linter enforces the
`api-layers.md` direction.

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
