# STORAGE CONTRACT — handoff to the methodist agent

> **Audience: the content author (methodist), not a backend engineer.**
> This document is the contract you fill with real lessons and exercises. The
> backend, DB schema, sandbox, and ingest tool already exist and are frozen for
> this stage. You add **content**; you do not change schema or code.

## The shape of content

```
Lesson (markdown body)                                [bilingual prose: en + ru]
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
- **All learner-facing PROSE is bilingual (English + Russian).** Real published
  content MUST provide both locales for every prose field. See "Bilingual
  content" below.

## Bilingual content (en + ru) — REQUIRED for real content

Learner-facing **prose** exists in both English (`en`) and Russian (`ru`):

| Translated (must give both `en` + `ru`) | Language-neutral (single value) |
|---|---|
| lesson `title` | exercise `starter_code` |
| lesson `body_md` | exercise `solution_code` |
| exercise `title` | exercise `solution_module` |
| exercise `statement_md` | each test's `filename` / `content` / `is_hidden` |

Code is code: pytest names, assertion messages, starter and reference solutions
are NOT translated. The API returns **both locales in one payload** and the
frontend switches language instantly client-side (no reload, no re-fetch).

**Fallback:** if you omit a locale, ingest fills it from the present locale
(English preferred) rather than failing — so a legacy single-locale fixture
still loads. This is a safety net, NOT a license to ship one locale: real
content must author both.

## How content is stored (DB schema)

| Table | Field | Type | Req? | Meaning |
|---|---|---|---|---|
| `lesson` | `slug` | str, unique | ✅ | Stable id used by ingest + URL (`?lesson=<slug>`). |
| | `position` | int | – | Curriculum ordering (default 0). |
| | `is_published` | bool | – | `false` for drafts/placeholders, `true` for real content. |
| `lesson_translation` | `(lesson_id, locale)` | unique | ✅ | One row per locale (`en`, `ru`). |
| | `title` | str | ✅ | Lesson title for this locale. |
| | `body_md` | str (markdown) | ✅ | Lesson text for this locale; rendered verbatim. |
| `exercise` | `slug` | str | ✅ | Unique within its lesson. |
| | `starter_code` | str | – | Pre-filled editor content, language-neutral (default empty). |
| | `solution_code` | str \| null | – | **Hidden reference solution** (self-validates tests). NEVER exposed by the API. Optional but recommended for real content. |
| | `solution_module` | str | – | Module name the user's code is saved as (default `solution`). |
| | `position` | int | – | Order within the lesson. |
| `exercise_translation` | `(exercise_id, locale)` | unique | ✅ | One row per locale (`en`, `ru`). |
| | `title` | str | ✅ | Exercise title for this locale. |
| | `statement_md` | str (markdown) | ✅ | Task statement for this locale. |
| `exercise_test` | `filename` | str | ✅ | File written into the sandbox; **must match pytest discovery** (`test_*.py` or `*_test.py`). |
| | `content` | str (python) | ✅ | Full pytest source. May `from <solution_module> import ...`. |
| | `is_hidden` | bool | – | If `true`, the test runs but its **source is never sent to the frontend** (use for anti-cheat checks). |
| | `position` | int | – | Order; tests run deterministically by position. |

**Two fields are stored but NEVER sent to the frontend** (anti-cheat): hidden
test `content` (when `is_hidden=true`) and `solution_code` (always). The lesson
API response has no field for either; assertions in the test suite guard this.

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

Translated prose fields (`title`, `body_md`, exercise `title`/`statement_md`)
are objects keyed by locale: `{"en": "...", "ru": "..."}`. Code-bearing fields
stay single-valued strings.

```json
{
  "slug": "decorators-basics",
  "title": { "en": "Decorators — the basics", "ru": "Декораторы — основы" },
  "body_md": { "en": "# Decorators\n\n...", "ru": "# Декораторы\n\n..." },
  "position": 1,
  "is_published": true,
  "exercises": [
    {
      "slug": "timing-decorator",
      "title": { "en": "Write a timing decorator", "ru": "Напишите декоратор таймера" },
      "statement_md": { "en": "Implement `timed` so that ...", "ru": "Реализуйте `timed`, чтобы ..." },
      "starter_code": "def timed(fn):\n    ...\n",
      "solution_code": "import functools, time\n\ndef timed(fn):\n    ...\n",
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
`starter_code=""`, `solution_code=null`, `solution_module="solution"`,
`is_hidden=false`.

**Locale handling on ingest:**

- A prose field may be a `{"en", "ru"}` object (canonical) **or** a bare string
  (legacy single-locale). A bare string is stored under every locale.
- Omitting a locale inside the object is tolerated — the present locale (English
  preferred) fills the gap — but real content MUST provide both.
- `solution_code` accepts the legacy key `_solution_code` as an alias, so a
  fixture authored before this field was formalised still ingests. **Use
  `solution_code` for new content.**

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
