# STORAGE CONTRACT — handoff to the methodist agent

> **Audience: the content author (methodist), not a backend engineer.**
> This document is the contract you fill with real lessons and exercises. The
> backend, DB schema, sandbox, and ingest tool already exist and are frozen for
> this stage. You add **content**; you do not change schema or code.

## The shape of content

```
Lesson (markdown body)
  └── Exercise (task statement + starter code)        [1 lesson → many exercises]
        └── ExerciseTest (one pytest file)            [1 exercise → many tests]
```

Rules the platform expects:

- A **lesson with zero exercises is incomplete** content. The DB allows it (so
  skeletons can exist), but a real published lesson must have ≥1 exercise.
- An **exercise must have ≥1 ExerciseTest**, otherwise "Check" can never pass
  (the runner treats "0 tests collected" as *not passed*).
- Tests `import` the learner's code as a module named by
  `Exercise.solution_module` (default `solution`). So a test writes
  `from solution import answer`. The learner's submitted code is saved as
  `<solution_module>.py` inside the sandbox.

## How content is stored (DB schema)

| Table | Field | Type | Req? | Meaning |
|---|---|---|---|---|
| `lesson` | `slug` | str, unique | ✅ | Stable id used by ingest + URL (`?lesson=<slug>`). |
| | `title` | str | ✅ | Lesson title. |
| | `body_md` | str (markdown) | ✅ | Lesson text; rendered verbatim by the page. |
| | `position` | int | – | Curriculum ordering (default 0). |
| | `is_published` | bool | – | `false` for drafts/placeholders, `true` for real content. |
| `exercise` | `slug` | str | ✅ | Unique within its lesson. |
| | `title` | str | ✅ | Exercise title. |
| | `statement_md` | str (markdown) | ✅ | Task statement above the editor. |
| | `starter_code` | str | – | Pre-filled editor content (default empty). |
| | `solution_module` | str | – | Module name the user's code is saved as (default `solution`). |
| | `position` | int | – | Order within the lesson. |
| `exercise_test` | `filename` | str | ✅ | File written into the sandbox; **must match pytest discovery** (`test_*.py` or `*_test.py`). |
| | `content` | str (python) | ✅ | Full pytest source. May `from <solution_module> import ...`. |
| | `is_hidden` | bool | – | If `true`, the test runs but its **source is never sent to the frontend** (use for anti-cheat checks). |
| | `position` | int | – | Order; tests run deterministically by position. |

`submission` and `progress` are written by the platform at runtime — **you never
author those**.

## How a test's pytest tests are represented

- **One row per pytest file.** An exercise with two test files = two
  `exercise_test` rows. Each `content` is a complete, standalone `test_*.py`.
- Tests import the solution module: `from solution import <name>`.
- The sandbox runs `pytest` over all of an exercise's files together. The
  exercise passes only when **every** collected test passes and at least one
  test was collected.
- Keep each test file independent (no shared fixtures across files for now —
  there is no `conftest.py` ingest field yet; see "next stage").

## How starter code is stored

Plain string in `exercise.starter_code`. It is the initial editor content; the
learner edits and submits it. Leave empty for a blank editor.

## How to add new content — the ingest format + tool

Author a **JSON file** matching this shape (one file = one lesson), then run the
ingest CLI. Ingest is **upsert by lesson `slug`** (re-running replaces the
lesson and all its exercises/tests).

```json
{
  "slug": "decorators-basics",
  "title": "Decorators — the basics",
  "body_md": "# Decorators\n\n...markdown lesson...",
  "position": 1,
  "is_published": true,
  "exercises": [
    {
      "slug": "timing-decorator",
      "title": "Write a timing decorator",
      "statement_md": "Implement `timed` so that ...",
      "starter_code": "def timed(fn):\n    ...\n",
      "solution_module": "solution",
      "position": 0,
      "tests": [
        {
          "filename": "test_timed_returns_value.py",
          "content": "from solution import timed\n\n\ndef test_passes_through():\n    @timed\n    def f():\n        return 7\n    assert f() == 7\n",
          "is_hidden": false,
          "position": 0
        }
      ]
    }
  ]
}
```

Ingest it:

```bash
uv run --directory services/api python -m python_coach.seed path/to/your_lesson.json
# or for the placeholder fixture:
make api-seed
```

Field defaults if omitted: `position=0`, `is_published=false`,
`starter_code=""`, `solution_module="solution"`, `is_hidden=false`.

## Authoring guidance (content quality is YOUR remit, not the architect's)

- Write tests the way an AQA engineer would: clear names, one behaviour per test,
  helpful assertion messages (they surface verbatim in the results panel).
- Use `is_hidden=true` for edge-case checks you don't want the learner to read
  before solving.
- The runner has **only pytest** available — no third-party libs are importable
  inside the sandbox by design. If a lesson needs a library, that is a
  next-stage change to the sandbox image, not something to assume.

## What you must NOT do

- Do not change the DB schema, models, API, or sandbox.
- Do not put secrets or network-dependent tests in `content` (the sandbox has
  **no network**; such tests will always fail).
- Do not rely on writing files outside the test's working dir (root FS is
  read-only; only the ephemeral `/work` tmpfs is writable).
