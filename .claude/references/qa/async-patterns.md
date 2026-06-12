# Async Playwright review

Playwright has two Python APIs: sync (`playwright.sync_api`) and async (`playwright.async_api`). They are not interchangeable — pick one and stick with it per project.

## Detection

Tell which API the code uses:
- `from playwright.sync_api import ...` → sync
- `from playwright.async_api import ...` → async
- Tests are `async def` and fixtures use `pytest_asyncio.fixture` → async
- Tests are `def` (regular) → sync

**Mixed usage is a bug.** Flag it immediately.

## Common async bugs

### 1. Missing `await`
```python
# BAD — returns coroutine object, does nothing
async def test_login(page):
    page.goto("/login")  # missing await!
    page.get_by_label("Email").fill("user@example.com")

# GOOD
async def test_login(page):
    await page.goto("/login")
    await page.get_by_label("Email").fill("user@example.com")
```

This often passes silently — the coroutine never runs, but the test also doesn't fail on the missing action. Then later assertions fail with confusing errors.

**Review check:** every Playwright call in async code should have `await`, except:
- `page.on(...)` (sync event registration)
- `page.locator(...)` (returns locator, doesn't trigger action)
- `page.get_by_*(...)` (same — returns locator)

Rule: if it triggers network, DOM interaction, or waits — it needs `await`.

### 2. Wrong fixture decorator
```python
# BAD — pytest-asyncio won't handle this
@pytest.fixture
async def logged_in_page(page):
    await page.goto("/login")
    ...
    yield page

# GOOD
import pytest_asyncio

@pytest_asyncio.fixture
async def logged_in_page(page):
    await page.goto("/login")
    ...
    yield page
```

With `pytest-asyncio` mode = "strict" (default), async fixtures need `@pytest_asyncio.fixture`. In mode "auto", `@pytest.fixture` works. Check `pyproject.toml` / `pytest.ini` for `asyncio_mode`.

### 3. `expect` is also async
```python
# BAD
expect(page.locator(".toast")).to_be_visible()

# GOOD
from playwright.async_api import expect
await expect(page.locator(".toast")).to_be_visible()
```

In async API, `expect` assertions are coroutines. Missing `await` means no retry happens and assertion effectively passes silently.

### 4. `asyncio.sleep` misuse
Same story as `time.sleep` in sync — almost always wrong. Wait for an event, not for a duration.

### 5. Event loop scope in fixtures
```python
# Can cause "Event loop is closed" errors
@pytest_asyncio.fixture(scope="session")
async def browser():
    ...
```

By default pytest-asyncio creates a new event loop per test. Session-scoped async fixtures need a session-scoped event loop:
```python
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

Or use `pytest-asyncio` >= 0.23 with `asyncio_default_fixture_loop_scope = "session"` in config.

### 6. `page.on` handlers that call async code
```python
# BAD — sync handler, can't await
page.on("dialog", lambda d: d.accept())

# BAD — creates coroutine, never awaited
page.on("dialog", async_handler)

# GOOD — schedule the coroutine
page.on("dialog", lambda d: asyncio.create_task(handle_dialog(d)))
```

### 7. Context managers need `async with`
```python
# BAD
with page.expect_response("**/api/users") as response_info:
    await page.get_by_role("button").click()

# GOOD
async with page.expect_response("**/api/users") as response_info:
    await page.get_by_role("button").click()
response = await response_info.value
```

## Sync vs async — why choose?

Don't let the reviewee mix. Reasons to pick one:
- **Sync:** simpler, works with plain pytest, enough for 95% of UI tests.
- **Async:** better when running tests against many pages in parallel within one test, or when test logic itself needs concurrency (WebSocket monitoring alongside UI actions).

If the project is starting out and there's no strong reason for async — flag the added complexity.
