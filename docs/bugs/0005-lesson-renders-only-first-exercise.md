# Bug 0005 — lesson page rendered only the first exercise

**Severity:** high (progression-blocking) — a learner could never complete any
multi-exercise lesson, so every subsequent lesson stayed permanently locked.
**Component:** `services/api/static/app.js` (lesson rendering).
**Status:** FIXED (2026-06-16) — the page renders every exercise of the lesson.

## Symptom
The owner solved the one visible exercise of lesson 1 ("solved (1 attempt)") but
lesson 2 stayed locked. Investigation: lesson 1 has 4 exercises; only 1 was solved
(1/4). Gating was correct — but the UI only ever showed exercise 1, with no way to
reach exercises 2–4, so the lesson could never be completed.

## Cause
`app.js` did `currentExercise = lessonData.exercises[0]` and rendered just that one,
even though `GET /api/lessons/{slug}` returns all exercises.

## Fix
Render each exercise as its own block (title, statement, dedicated CodeMirror
editor, Check, results, solved badge), independently checkable; show a lesson-level
"X / N solved" counter and reflect already-solved exercises on load. Completion and
the "Next lesson →" button appear only when ALL exercises are solved. Rendering
logic extracted to `static/exercise.js`. Regression tests in
`tests/ui/test_multi_exercise.py` (renders all blocks; completion only at N/N).

Note: the gating/completion backend was already correct and was not changed.
