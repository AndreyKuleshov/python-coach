# Flakiness checklist

Flakiness in Playwright almost always comes from one of these root causes. Check each section against the code under review.

## 1. Hard waits (almost always wrong)

### `time.sleep()` / `page.wait_for_timeout()`
- **Red flag:** any occurrence. Zero exceptions in normal test code.
- **Why it's bad:** either too short (flaky) or too long (slow). Both hide the real timing problem.
- **Fix:** use web-first assertions (`expect(locator).to_be_visible()`), `locator.wait_for(state=...)`, or `page.wait_for_url()`.
- **Rare exception:** waiting for pure time-based UI (animations you explicitly can't assert on, debouncers). Even then, prefer asserting on the post-debounce state.

### `asyncio.sleep()` in async tests
Same as above. If you see it, ask what event the test is actually waiting for, then wait on that event.

## 2. Assertions that don't auto-retry

```python
# BAD — one-shot check, no retry
assert page.locator(".toast").is_visible()
assert page.locator(".balance").text_content() == "€100"

# GOOD — web-first assertions retry until timeout
expect(page.locator(".toast")).to_be_visible()
expect(page.locator(".balance")).to_have_text("€100")
```

`is_visible()`, `text_content()`, `inner_text()`, `count()` return the value *right now*. `expect(...)` polls until the condition is met or timeout expires. Always use `expect` for final assertions on async-rendered UI.

## 3. Race conditions around navigation

```python
# BAD — click returns immediately, URL check may run before navigation completes
page.get_by_role("button", name="Submit").click()
assert page.url == "/dashboard"

# GOOD
page.get_by_role("button", name="Submit").click()
page.wait_for_url("**/dashboard")
# or: expect(page).to_have_url(re.compile(r"/dashboard"))
```

Also watch for:
- `expect_navigation` / `expect_response` context managers used incorrectly (must wrap the *trigger*, not be called after)
- Clicking a link and immediately interacting with the next page without waiting for load

## 4. Shared state between tests

- **Module-level variables** mutated by tests.
- **Class attributes** on a test class that carry state between methods.
- **`session`-scoped fixtures** returning mutable objects (a logged-in page shared across tests = guaranteed flake in parallel runs).
- **External state** (DB rows, files, queues) not cleaned up. If test A leaves a user in the DB and test B assumes a clean state — order-dependent flakiness.
- **Browser storage state** reused without `context.clear_cookies()` or fresh context.

Rule of thumb: if you can't shuffle test order or run with `pytest-xdist -n auto` without failures, tests are not isolated.

## 5. Selector instability

Flaky selectors cause intermittent "element not found":
- Selectors that depend on position (`nth-child`, `:first-of-type`) when order isn't guaranteed.
- XPath with full path from root.
- Text selectors with text that varies by locale / dynamic content.
- CSS classes that look generated (`._aX3kL`, `.css-1abc`) — these change on every build.

See `selectors.md` for the full selector hierarchy.

## 6. Network and timing assumptions

- Tests that assume API responds within X ms. Use `page.route()` to stub if you need determinism.
- Tests that count network requests without deduplication (SPAs often retry on focus).
- Animations not disabled — elements report visible before they've finished transitioning in. Consider `page.add_init_script()` to disable CSS transitions in tests, or use `expect().to_be_visible()` which handles this for most cases.

## 7. Event handlers and listeners not cleaned up

```python
# BAD — handler leaks between tests if page is reused
page.on("dialog", lambda d: d.accept())

# GOOD — in a fixture with teardown, or use page.once() for one-shot
```

`page.on()` accumulates listeners. In session-scoped contexts this leaks across tests.

## 8. Retry logic hiding real bugs

- `@pytest.mark.flaky(reruns=3)` on a specific test → almost always means the test is covering up a real bug. Ask why.
- Global retry configured in `conftest.py` → masks flakiness instead of fixing it. Useful as a safety net in CI, but if it's firing often, the suite needs work.
- Screenshots/traces not captured on failure → you can't debug flakes you can't see. Configure `--tracing=retain-on-failure` in CI.

## 9. Browser / context lifecycle

- Reusing `page` across tests → cookies, localStorage, open tabs all leak.
- Best pattern: **session-scoped browser, function-scoped context, function-scoped page** (this is what `pytest-playwright` does by default).
- Authenticated state should be loaded via `storage_state` from a JSON file created once per session, not by logging in every test.

## 10. Timeout configuration

- Global action timeout too low (< 5s) → flaky on slow CI.
- Global navigation timeout unset → uses Playwright default (30s), usually fine, but explicit is better.
- Per-test timeout used to mask slow tests (`@pytest.mark.timeout(120)`) → investigate, don't just extend.

## Quick review pattern

When reviewing, grep/search for these strings as fast signals:
```
time.sleep
wait_for_timeout
asyncio.sleep
\.is_visible\(\)\s*(==|!=|\s*assert)   # is_visible used as final assertion
@pytest\.mark\.flaky
reruns=
```

Most flaky test suites show 80% of issues in these searches alone.
