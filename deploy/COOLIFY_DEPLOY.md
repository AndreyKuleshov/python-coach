# Coolify deploy plan — python-coach

Target: the owner's **Coolify v4.0.0** on Contabo (`COOLIFY_HOST`, IP `161.97.89.82:8000`),
Traefik proxy + Let's Encrypt. This document is the authoritative ordered plan for
**Phase B** (the live deploy). Phase A authored the artifacts below and did only
read-only `GET`s against the Coolify API. **No live resource has been created.**

> Phase B requires explicit owner sign-off on two items flagged below:
> (1) the `/var/run/docker.sock` mount the sandbox grader needs, and
> (2) creating live infra (Postgres + the app) on the production host.

## Confirmed inventory (read-only probe, Phase A)

| Thing | Value |
|---|---|
| Coolify version | `4.0.0` |
| Server | `localhost`, uuid `h7jfzakz4yaed9fnfgv8q4v0`, `is_coolify_host=true`, IP `host.docker.internal` |
| Server network | `coolify` |
| Destination (StandaloneDocker) | uuid `gchal4l1ep7hnhsnvvqkctr0` |
| Project | `gigs`, uuid `u142qntji7qvazr1qpfdpm4l`, `environment_id=1` (name `production`) |
| Databases | **none** (`GET /api/v1/databases` → `[]`) |
| Services | none |
| Host SSH private key | uuid `u7z93pwqrn64i2qr6n3kopba` ("localhost's key") — usable to `ssh`/`docker build` on the host |
| Reference app | `gigs-bot` uuid `y1345hhcrnbhtey4y8jddkqa`, `build_pack=dockerfile`, public repo `AndreyKuleshov/gigs_bot`, `fqdn=https://gigs-bot.duckdns.org`, `ports_exposes=8000` |
| Our app repo | `AndreyKuleshov/python-coach` — **public** (no deploy key / GitHub App needed) |

## What ships vs what never ships

- **Ships:** the API as a production image (`services/api/Dockerfile`, multi-stage,
  non-root uid 10001, locked runtime deps only), serving the static SPA; the
  `python-coach-sandbox` image on the host; a Postgres database; Alembic migrations
  applied on release.
- **Never ships:** `.claude/` (harness), `sources/`, `docs/`, `tests/`, `fixtures/`
  (raw authoring inputs), `deploy/` compose, build docs. Enforced by the repo
  `.dockerignore` (build context = repo root). Verified in Phase A: the built image
  contains none of these (`docker run ... sh -c 'ls /app/...'`).

---

## Decision 1 (NEEDS OWNER APPROVAL) — the sandbox grader + docker.sock

The API grades each submission by calling the host `docker` CLI:
`docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges
--memory/--memory-swap --cpus --pids-limit 128 --tmpfs /work ... python-coach-sandbox:...`
(see `services/api/src/python_coach/clients/sandbox.py`). For this to work **inside a
Coolify-managed container** two things must hold on the Contabo host:

1. **The `python-coach-sandbox` image must exist on the host.** It is NOT pulled from a
   registry by the app; it is referenced by local tag. Build it on the host (the
   sandbox build context is tiny and has no secrets):
   ```
   # over SSH to the Contabo host (uses the existing host key)
   git clone https://github.com/AndreyKuleshov/python-coach /tmp/pc && \
   docker build -t python-coach-sandbox:latest /tmp/pc/services/sandbox && rm -rf /tmp/pc
   ```
   Set `SANDBOX_IMAGE=python-coach-sandbox:latest` in the app env to match.

2. **The API container must reach the host Docker daemon** by mounting
   `/var/run/docker.sock` into the API container (plus the host `docker` CLI, which the
   slim image lacks — see "docker CLI in the image" below).

### The security tradeoff (state it plainly)

Mounting `/var/run/docker.sock` gives the API container **full control of the host
Docker daemon** — which is effectively **root on the host** (it can start privileged
containers, mount the host filesystem, etc.). This widens the trust boundary: today the
API process is already trusted (it spawns containers); on Coolify that trust now extends
to "can drive host Docker". The mitigations that remain in force:

- **Untrusted user code never gains the socket.** The socket is mounted into the *API*
  container only. Each submission still runs in a **separate** sandbox container with
  `--network none`, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`,
  memory/CPU/pids caps, and a host-side wall-clock kill. User code cannot see or reach
  the socket; it sees only the locked-down sandbox container.
- The threat that grows is **a compromise of the API process itself** (e.g. an RCE in
  FastAPI/our code) escalating to host-root via the socket. For a single-owner personal
  platform this is the documented, accepted MVP posture (README "Threat model" already
  records container-isolation-via-host-daemon as the chosen level).

### Safest workable option on the fixed stack

Socket mount + the existing strict per-run flags (above). Do **not** add a TCP-exposed
daemon. If the owner wants to shrink the blast radius later (a Phase-C item, needs
stack approval per `stack.md`): a dedicated runner host, a rootless/socket-proxy
(`tecnativa/docker-socket-proxy` restricted to `containers`/`images` POST), or
gVisor/Kata. None of these are adopted now.

**In Coolify**, the socket mount + the host docker CLI are configured as a *persistent
storage / volume mount* on the application:
- `/var/run/docker.sock:/var/run/docker.sock`
- `/usr/bin/docker:/usr/bin/docker:ro` (bind the host CLI; the slim runtime image has no
  docker client) **and** the matching libs, OR set `DOCKER_BIN` to a static docker
  binary baked in. Recommended: bind-mount the host `docker` CLI read-only and keep
  `DOCKER_BIN=docker`. Confirm the host CLI is dynamically linked against libs present
  in the runtime image (bookworm slim) during Phase B; if not, fall back to copying a
  static `docker` binary into the image (a follow-up image tweak, no stack change).

> Phase B does not proceed past app creation until the owner approves this mount.

---

## Decision 2 — Postgres (must be created; none exists)

Create a managed Postgres resource in the `gigs` project on the host server, then wire
its **internal** connection string into the app with the `+asyncpg` driver.

- Coolify exposes an internal hostname on the `coolify` network for the DB. After
  creation, read it from `GET /api/v1/databases/{uuid}` (`internal_db_url` /
  the assembled host). The app's `DATABASE_URL` must be the **internal** URL (private
  network, never the public-facing one) and must use the **`postgresql+asyncpg://`**
  scheme (Coolify returns a plain `postgres://`/`postgresql://` URL — rewrite the
  scheme to `postgresql+asyncpg://`).
- Postgres image: pin `postgres:17.2-bookworm` (matches local `deploy/docker-compose.yml`).

## Decision 3 — Domain / HTTPS

Proposed subdomain: **`python-coach.duckdns.org`** (sibling of the existing
`gigs-bot.duckdns.org`). Coolify + Traefik issues the Let's Encrypt cert automatically
once the FQDN is set and DNS points at the host. **Owner must confirm the subdomain and
that the DuckDNS record resolves to the Contabo IP.** `PUBLIC_BASE_URL` must equal the
chosen `https://...` FQDN (it is baked into email confirmation links).

---

## Environment / secrets surface (set in Coolify env, never in the image)

Every value comes from the Coolify application env (secrets manager); none is baked into
the image or committed. `services/api/.env.example` documents the surface with
placeholders only.

| Var | Source / value | Secret? |
|---|---|---|
| `DATABASE_URL` | internal Coolify Postgres URL, scheme rewritten to `postgresql+asyncpg://` | yes |
| `JWT_SECRET` | generate a fresh random 32+ byte secret (`openssl rand -hex 32`) | **yes** |
| `JWT_ACCESS_TOKEN_MINUTES` | `1440` | no |
| `JWT_CONFIRM_TOKEN_MINUTES` | `60` | no |
| `SANDBOX_IMAGE` | `python-coach-sandbox:latest` (built on host, Decision 1) | no |
| `SANDBOX_WALL_TIMEOUT_SECONDS` | `10` | no |
| `SANDBOX_MEMORY_LIMIT` | `256m` | no |
| `SANDBOX_CPU_LIMIT` | `1.0` | no |
| `DOCKER_BIN` | `docker` (host CLI bind-mounted, Decision 1) | no |
| `SMTP_HOST` | real SMTP host, or **empty** to log the confirmation link via structlog | no |
| `SMTP_PORT` | `587` | no |
| `SMTP_USER` / `SMTP_PASSWORD` | SMTP creds (empty when `SMTP_HOST` empty) | **yes** |
| `SMTP_FROM` | `no-reply@<domain>` | no |
| `PUBLIC_BASE_URL` | `https://python-coach.duckdns.org` (must match the FQDN) | no |
| `OPENAI_API_KEY` | OpenAI key, or **empty** to disable AI features (graceful 503) | **yes** |
| `OPENAI_MODEL` | `gpt-4o-mini` | no |

`OPENAI_FAKE` is a test-only seam — **do not set it in production**.

> If a real secret is ever found in a tracked file, STOP and flag it. Phase A confirmed
> only `.env.example` placeholders are committed; real `.env` is gitignored.

---

## Phase B — exact ordered API calls

All calls via `bash /tmp/coolify.sh <METHOD> <path> [json-body]` (reads host+token from
`services/api/.env`). `deploy/coolify-deploy.sh` runs these in order, guarded behind an
explicit `--go` flag (it prints the plan and exits otherwise). Replace `<...>` with the
values resolved at run time.

### 1. Create Postgres

```
POST /api/v1/databases/postgresql
{
  "server_uuid": "h7jfzakz4yaed9fnfgv8q4v0",
  "project_uuid": "u142qntji7qvazr1qpfdpm4l",
  "environment_name": "production",
  "name": "python-coach-db",
  "image": "postgres:17.2-bookworm",
  "postgres_user": "coach",
  "postgres_db": "coach",
  "instant_deploy": true
}
```
Then `GET /api/v1/databases/{db_uuid}` → capture the **internal** URL; rewrite scheme to
`postgresql+asyncpg://` for `DATABASE_URL`. (Let Coolify generate `postgres_password`;
read it back from the DB resource rather than committing one.)

### 2. Create the application from the public repo (dockerfile build pack)

```
POST /api/v1/applications/public
{
  "project_uuid": "u142qntji7qvazr1qpfdpm4l",
  "environment_name": "production",
  "server_uuid": "h7jfzakz4yaed9fnfgv8q4v0",
  "destination_uuid": "gchal4l1ep7hnhsnvvqkctr0",
  "name": "python-coach",
  "git_repository": "https://github.com/AndreyKuleshov/python-coach",
  "git_branch": "main",
  "build_pack": "dockerfile",
  "dockerfile_location": "/services/api/Dockerfile",
  "ports_exposes": "8000",
  "domains": "https://python-coach.duckdns.org",
  "instant_deploy": false
}
```
Capture the returned application `uuid` as `APP_UUID`. (Build context for the dockerfile
build is the repo root, where `.dockerignore` lives — matches how the image was verified
in Phase A.)

### 3. Set the application env (one PATCH per var, or bulk)

For each row in the env table above:
```
POST /api/v1/applications/{APP_UUID}/envs
{ "key": "DATABASE_URL", "value": "postgresql+asyncpg://coach:<pw>@<internal-host>:5432/coach", "is_preview": false }
```
Secrets (`JWT_SECRET`, `OPENAI_API_KEY`, `SMTP_PASSWORD`, `DATABASE_URL`) are entered
here, never in the repo. Set `is_build_time=false` for all (runtime-only).

### 4. (NEEDS APPROVAL) attach the docker.sock + host docker CLI mounts

Configure persistent storage / volume mounts on `{APP_UUID}` (Decision 1):
`/var/run/docker.sock:/var/run/docker.sock` and `/usr/bin/docker:/usr/bin/docker:ro`.
The exact v4 endpoint is the application's "persistent storage" mount; do this in the
Coolify UI if the API field shape is uncertain, then re-confirm via GET. **Owner approval
gate.**

### 5. Build the sandbox image on the host (Decision 1)

SSH to the host and `docker build -t python-coach-sandbox:latest .../services/sandbox`
(command above). Must complete **before** the first submission is graded.

### 6. Deploy

```
GET /api/v1/deploy?uuid={APP_UUID}&force=false
```
(or `POST /api/v1/applications/{APP_UUID}/restart` after first deploy.) The Dockerfile
`CMD` runs uvicorn on `0.0.0.0:8000`; Traefik routes the FQDN to it.

### 7. Migrate + seed on release

Run inside the app container (Coolify "Execute Command", or an SSH `docker exec`):
```
cd /app && alembic upgrade head     # verified working in Phase A
```
Seed real methodist content (NOT the throwaway placeholder). `fixtures/` is excluded from
the image, so seeding runs from a checkout on the host or a one-off job that mounts the
fixtures:
```
# on the host, against the same DATABASE_URL
uv run --directory services/api python -m python_coach.seed fixtures/<real_lesson>.json
```
Decide with the methodist which fixtures are production content before seeding.

### 8. Verify

- `GET https://python-coach.duckdns.org/healthz` → `{"status":"ok"}` (Phase A confirmed
  this responds once the app boots with only runtime env).
- Register → confirm (link logged if SMTP empty) → login → open a lesson → submit →
  confirm a sandbox container spawns and grades.

---

## Rollback

- **App:** Coolify keeps previous deployments — redeploy the prior commit/image from the
  app's Deployments tab, or `GET /api/v1/deploy?uuid={APP_UUID}` pinned to the last good
  commit. The image carries no state, so rollback is just redeploy-previous.
- **DB:** migrations are forward-only here; before a risky release take a logical dump
  (`pg_dump` via the DB container). The `auth` migration deletes pre-auth
  submission/progress rows — irrelevant in prod (fresh DB) but note it.
- **Teardown (if the deploy is abandoned):** `DELETE /api/v1/applications/{APP_UUID}`
  then `DELETE /api/v1/databases/{db_uuid}`. Not part of normal rollback.

## Open items for the owner before Phase B

1. **Approve the `/var/run/docker.sock` mount** (Decision 1) — the central security
   tradeoff. Without it, grading does not work on Coolify.
2. **Approve creating live infra** (Postgres + app) on the production host.
3. **Confirm the subdomain** `python-coach.duckdns.org` (or supply another) and that DNS
   points at the Contabo IP.
4. **SMTP:** provide real SMTP creds, or accept the log-the-link fallback (single-owner
   confirmations).
5. **OpenAI:** provide a production `OPENAI_API_KEY`, or accept AI features disabled (503).
6. **Seed content:** which methodist fixtures are production lessons.
