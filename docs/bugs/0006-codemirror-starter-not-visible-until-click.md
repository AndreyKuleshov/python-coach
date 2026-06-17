# Bug 0006 — CodeMirror starter code not visible until editor is clicked

**Severity:** medium (UX regression) — every exercise on every lesson page
appeared with an empty editor on load; the starter scaffold was only revealed
after the learner clicked or focused the editor widget.
**Component:** `services/api/static/exercise.js` (exercise block construction).
**Status:** FIXED (2026-06-17) — starter code is now painted on load with no
user interaction required.

## Symptom

Screenshots confirmed: immediately after navigating to a lesson page, each
exercise's CodeMirror editor box was visually empty. The moment the user
clicked inside any editor the starter code appeared. Refreshing the page
reproduced the same blank state; the content was always there (CodeMirror
held it internally) but was never rendered into the DOM without a user
interaction triggering CodeMirror's internal refresh.

## Cause

`_buildBlock()` in `exercise.js` creates the CodeMirror editor with
`CodeMirror.fromTextArea(ta, ...)` and immediately calls `cm.setValue(...)`.
The textarea is inside a DOM fragment that has not yet been attached to the
live document at that moment — `container.appendChild(block)` happens only
after `_buildBlock()` returns. CodeMirror performs its initial layout pass
(measure dimensions, paint lines) synchronously on mount, but when the
container element is detached, all measured sizes are zero and no line divs
are written to `.CodeMirror-code`. The first user interaction (click / focus)
triggers CodeMirror's `"focus"` handler which calls `refresh()` internally,
causing the deferred first paint — hence the "empty until click" symptom.

## Fix

After every exercise block has been appended to the live, visible container,
schedule a `requestAnimationFrame` callback that calls `cm.refresh()` on
every editor instance stored in `_editors`. The animation frame fires after
the browser has performed its next layout pass on the now-attached nodes, so
CodeMirror measures real dimensions and paints the starter code immediately.
No editor is rebuilt and no `setValue` is repeated, so locale-switch and
re-render are unaffected. Change is in `exercise.js` lines ~62–74
(immediately after the `for (const ex of …) { container.appendChild(…) }`
loop in `renderExercises`).
