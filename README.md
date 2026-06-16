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
      rest/{lessons,submissions,progress}/routes.py
    controllers/              use-cases; take unpacked primitives; no fastapi import
    storage/                  one Storage class, per-domain mixins, SQLModel tables
      models/{lesson,submission}.py
    clients/                  SandboxClient (Docker runner) + result dataclasses
    migrations/               Alembic (config in pyproject, no alembic.ini)
    seed.py                   lesson ingest CLI (the methodist's tool)
  static/                     single-page lesson UI (CodeMirror + marked, CDN)
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

`lesson` 1—∞ `exercise` 1—∞ `exercise_test`; `submission` and `progress` per
exercise. Timestamps are `TIMESTAMP WITH TIME ZONE`. `submission.result` is
JSONB holding the structured pytest verdict. Full field reference:
[`STORAGE_CONTRACT.md`](./STORAGE_CONTRACT.md).

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
2. **Alembic migrations** (`alembic upgrade head`).
3. **Sandbox Docker image** build.
4. **Seed** the placeholder lesson (upsert-by-slug — safe to re-run).
5. **uvicorn** on `:8000` — foreground, keeping the terminal live.

Then open `http://127.0.0.1:8000/?lesson=placeholder-intro`, write code, click
**Check**.

To stop: `Ctrl-C` (kills uvicorn), then `make dev-down` to tear down Postgres.

You can still run steps individually:

```bash
make deploy-up        # start Postgres only
make api-migrate      # alembic upgrade head
make sandbox-build    # build the sandbox Docker image
make api-seed         # load the THROWAWAY placeholder lesson
make api-run          # uvicorn on :8000
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
- **Auth / multi-user.** Single-user MVP; no `user_id`, no login.
- **Async grading / queue.** Submissions grade synchronously in-request. Heavy
  use would want a job queue (Redis) + a `PENDING → result` poll flow (the
  schema already has `PENDING` and a `GET /submissions/{id}`).
- **Hardened sandbox.** gVisor/Kata/seccomp, a dedicated runner host, image with
  extra libs, `conftest.py` support per exercise.
- **Progress analytics & lesson navigation.** Only per-exercise progress + a
  single-exercise page exist; no curriculum index, no completion dashboards.
- **Allure / Playwright UI tests & httpx API integration tests.** Owned by the
  `qa` agent. Current tests are unit-level only.
- **Rate limiting / abuse controls** on the submit endpoint.

## Open questions and assumptions

**Assumptions made:**
1. Single user, no auth — taken from the mandate/stack.
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
