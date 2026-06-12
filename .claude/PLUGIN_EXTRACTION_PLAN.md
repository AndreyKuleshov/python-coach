# Plan: extract reusable agents into a plugin dependency

Status: **deferred — do NOT extract yet.** Revisit after the architect's first real
end-to-end run, once the agent prompts have stabilised. Recorded 2026-06-12.

## Idea

Separate the project-specific *what/standards* from the reusable *how/workers*.
The architect (project vision) + project rules define the task; a versioned
**dependency** supplies generic worker agents that execute it. A project can still
override any worker by shadowing its name locally.

## Why it works (Claude Code facts, confirmed)

- **Override precedence:** managed > CLI `--agents` > **project `.claude/agents/`** >
  **user `~/.claude/agents/`** > **plugin agents**. Same `name` → project wins. So
  global/plugin defaults are safe to ship and override per project.
- **A globally-installed agent reads the CURRENT project's `.claude/rules/`** (working
  dir = project). This is the whole point: generic worker + project-supplied standards,
  natively, no path hacks.
- Rules *can* live at user level too, but we keep them project-local on purpose — they
  are the project's contract.

## The cut

| Stays project-local | Reusable (→ plugin) |
|---|---|
| `python-platform-architect` (embodies this product's vision) | `coder` |
| `methodist` (Python/AQA/books content — NOT generic) | `code-reviewer` |
| Project rules: `stack.md`, `api-layers.md` | `qa` (see caveat) |
| Project `references/qa/pitfalls-journal.md` | Generic rules: `python`, `all-languages`, `docker`, `makefile`, `dotenv` |
| | Generic QA references: `flakiness-checklist`, `selectors`, `async-patterns`, `pom-patterns`, `allure`, `performance` |

Note vs. the original "everything global except architect+rules" idea: **methodist is
project-local** (domain-specific), and **rules split** — generic baseline travels,
project contract (`stack`, `api-layers`) does not.

## Implementation: plugin, not user-level

User-level (`~/.claude/agents/`) is the quick path but has no versioning, no namespacing,
and manual cross-machine sync. Use a **plugin + marketplace (git repo)** for a real,
versioned, shareable dependency installed via `/plugin install`.

### Known friction to solve at extraction time

- **No `${PLUGIN_ROOT}` for agents.** Agents cannot cleanly path to plugin-bundled
  files; only **skills** get `${CLAUDE_SKILL_DIR}`. So the generic QA references must be
  repackaged as a **skill inside the plugin**, and the `qa` agent reads them via that
  skill — i.e. `qa` becomes agent + bundled skill. The project-local pitfalls journal
  stays separate.
- **Plugin agent frontmatter can't include** `hooks`, `mcpServers`, or `permissionMode`
  (security). Our agents don't use these, so fine — but the deferred pre-commit Stop-hook
  (`post-edit-precommit.sh`) must stay project-local regardless.

## Sequence

1. **Now:** keep everything project-local (current state). Run the architect, iterate
   prompts on a real build. Extracting now means editing across a sync boundary exactly
   when churn is highest.
2. **After prompts stabilise:** promote the reusable workers + generic rules + QA-refs-as-skill
   into a plugin. The official "convert `.claude/agents/` → plugin" guide covers the
   migration, so deferring costs nothing.

## Revisit trigger

After the first successful architect run + at least one methodist lesson + one qa pass,
when the worker prompts have gone ~1 iteration without edits.
