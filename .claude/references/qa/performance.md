# Performance & parallelization review

E2E suites over ~50 tests need to run in parallel or they become unusable. Review with parallelization in mind even if the suite runs serially today.

## pytest-xdist compatibility

`pytest-xdist -n auto` runs tests across N workers. Tests must be isolated.

### Flag: shared state via filesystem
```python
# BAD — two workers race on the same file
TEMP_DOWNLOAD = "/tmp/invoice.pdf"

def test_download_invoice(page):
    page.locator("button.download").click()
    assert os.path.exists(TEMP_DOWNLOAD)
```

Fix: use `tmp_path` fixture, or Playwright's `page.wait_for_download()` which gives a unique path per download.

### Flag: hardcoded ports / resources
```python
# BAD
MOCK_SERVER_PORT = 8080
```
Use `unused_tcp_port` fixture from pytest-asyncio or pick dynamically.

### Flag: database rows without cleanup
Tests that INSERT without DELETE on teardown will fail on the Nth run or collide between workers. Use:
- Transaction rollback fixture (create → use → rollback)
- Unique identifiers (UUID in username) so tests don't collide
- Per-worker DB schemas (if using xdist, use `worker_id` fixture to pick a DB)

### Flag: session-scoped page / context / storage_state write
```python
# BAD — workers stomp on the same storage file
@pytest.fixture(scope="session")
def storage_state(browser):
    ...
    context.storage_state(path="auth.json")  # every worker writes here
    return "auth.json"
```
Use `worker_id` to pick per-worker filenames, or create state once per session outside xdist via `--dist loadfile` / session fixture with file lock.

## Browser / context lifecycle

The standard pattern for `pytest-playwright`:
- **browser:** session-scoped — expensive to start.
- **context:** function-scoped — cheap, isolates cookies/storage.
- **page:** function-scoped — one per test, fresh state.

Flag deviations:
- `context` with session scope → tests share cookies, localStorage, storage state. Huge source of order-dependent flakes.
- `browser` with function scope → ~1-2 seconds per test wasted on browser startup.

## Authenticated state via storage_state

If every test logs in via UI, setup time dominates runtime. Pattern:

```python
# conftest.py
@pytest.fixture(scope="session")
def authenticated_storage_state(browser, tmp_path_factory):
    path = tmp_path_factory.mktemp("auth") / "state.json"
    context = browser.new_context()
    page = context.new_page()
    page.goto("/login")
    page.get_by_label("Email").fill(ADMIN_EMAIL)
    page.get_by_label("Password").fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url("/dashboard")
    context.storage_state(path=path)
    context.close()
    return str(path)

@pytest.fixture
def authenticated_page(browser, authenticated_storage_state):
    context = browser.new_context(storage_state=authenticated_storage_state)
    page = context.new_page()
    yield page
    context.close()
```

Flag suites that log in via UI in every test and don't use `storage_state`.

## Slow operations inside tests

### Avoid
- Polling via `expect(...).to_be_visible(timeout=30000)` where 2-5s would suffice → default timeout propagates everywhere, masking real slowness.
- Chained long timeouts: if each `expect` waits up to 30s and there are 10 of them, worst-case test time is 5 min.
- `page.reload()` used to work around missing wait logic — each reload is 1-2s.

### Watch for
- Full login flow in every test (see storage_state above).
- Repeated `page.goto(BASE_URL)` when already there.
- Explicit waits right before a web-first assertion that would have waited anyway.

## Network stubs for non-critical flows

> **Project policy: mocking the backend is forbidden here** (see the `qa` agent's
> "banned workarounds"). Our suite drives the real stack — the FastAPI backend,
> the sandbox/pytest runner, and the DB — because the test is the oracle of the
> product. `page.route()` REST stubs, WS stubs, and `TEST_MODE` flags are not
> allowed. The only sanctioned "fake" is reversible DB seed/teardown in fixtures.
> The generic technique below is documented for context only; do **not** use it
> in this project's tests.

A generic Playwright suite that is checking UI behavior, not backend integration,
might stub the API:
```python
page.route("**/api/products", lambda route: route.fulfill(
    status=200,
    json={"items": [...]},
))
```

Saves network round-trips and makes tests deterministic — but **not here**, where
hitting the real backend (and the real sandbox) is the point.

## CI-specific

- Headless by default (obvious but worth confirming).
- `PWDEBUG=0` in CI (no debug inspector).
- Workers count: usually 2-4 workers on standard CI runners, more on beefy ones.
- Retry policy: `--reruns 1` (retry flaky failures once) is acceptable as a safety net; `--reruns 3` is hiding real flakiness.
- Sharding: for very large suites, `--shard` flag on different runners.

## Metrics to ask about (informational)

If reviewing a whole suite (not just a diff), worth asking:
- What's the p50 / p95 test duration?
- How long does the full suite take in CI?
- What's the flake rate (tests rerunning per night)?

These numbers drive priorities. A 40-minute suite with 2% flake rate needs different attention than a 4-minute suite with 15% flake rate.
