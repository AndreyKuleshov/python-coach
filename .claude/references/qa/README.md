# QA test-authoring references

On-demand reference material for the `qa` agent (and `code-reviewer` when reviewing
tests). These are **generic Playwright / pytest / Allure best practices** — read the
one relevant to the area you're working on; do not pre-load them all. The project's
own rules and policies live in `.claude/rules/*` and the `qa` agent prompt, which
override anything here on conflict.

| File | Read when… |
|---|---|
| `flakiness-checklist.md` | Writing or reviewing any test — the #1 audit. Catalog of flaky root causes (hard waits, non-retrying assertions, navigation races, shared state) + a grep pattern. |
| `selectors.md` | Choosing or reviewing locators. Priority hierarchy (role/label/test-id → CSS → XPath) and anti-patterns. |
| `async-patterns.md` | The code uses the async Playwright API. Missing-`await` bugs, async fixtures, `async with`, event-loop scope. |
| `pom-patterns.md` | Designing or reviewing Page Objects. Encapsulation, fluent navigation, component objects, what belongs in a POM (actions, not assertions). |
| `allure.md` | Adding or reviewing Allure annotations. Meaningful epic/feature/story, `@allure.step` in POMs, failure attachments via hook. |
| `performance.md` | The suite is large or runs under `pytest-xdist`. Isolation, browser/context lifecycle, `storage_state`, timeouts. |
| `pitfalls-journal.md` | Debugging a specific failing test — search by symptom. Append a dated entry after a non-obvious fix. |

Not copied from the source suite (project-specific): a scenario *scaffold* and the
*hard rules* — write our own once the test stack exists.
