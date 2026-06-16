"""Regression tests for the auth-gate access model + section/locale correctness.

Access model under test (CONTEXT.md): NO content is reachable while logged out.
Every route renders the inline auth gate (login/register) until a valid token
exists; the lessons list is its own authenticated /lessons view.

Guards:
  1. Logged-out `/` shows the auth form and NO lesson list / content.
  2. A logged-out deep link (/lessons or /?lesson=...) lands on the auth form,
     not the content (no leak).
  3. After login the lessons list appears (its own view); logout returns to the
     auth form.
  4. Authenticated section exclusivity + locale-pick correctness for titles.

The `functions-first-class` slug is a real, published lesson in the shared dev
DB used for the authenticated title assertions.
"""

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

from fixtures import SeededUser

pytestmark = [pytest.mark.ui]

# Real published lesson available in the shared dev DB.
_REAL_SLUG = "functions-first-class"
_REAL_LESSON_TITLE_EN = "First-class & higher-order functions; closures"
_REAL_EXERCISE_TITLE_EN = "Apply a function to each item"


# ── Helpers ─────────────────────────────────────────────────────────────────


def _fresh_page(browser: Browser) -> tuple[BrowserContext, Page]:
    """Open a fresh, empty browser context so localStorage never leaks."""
    ctx = browser.new_context()
    return ctx, ctx.new_page()


def _authed_page(browser: Browser, token: str) -> tuple[BrowserContext, Page]:
    """A fresh context pre-seeded with a bearer token (logged-in path)."""
    ctx = browser.new_context()
    page = ctx.new_page()
    page.add_init_script(f"window.localStorage.setItem('python-coach.token', '{token}');")
    return ctx, page


# ── 1. Logged out: the gate, never content ──────────────────────────────────


def test_logged_out_root_shows_auth_form_no_content(browser: Browser, live_server: str) -> None:
    """On `/` while logged out, the auth form shows and NO lesson content does."""
    ctx, page = _fresh_page(browser)
    try:
        page.goto(live_server + "/")
        # The auth gate + login form must be visible.
        expect(page.get_by_test_id("auth-gate")).to_be_visible()
        expect(page.get_by_test_id("login-form")).to_be_visible()

        # No content sections may render.
        expect(page.locator("#lesson-list-section")).to_be_hidden()
        expect(page.locator("#lesson-section")).to_be_hidden()
        expect(page.locator("#exercise-section")).to_be_hidden()
        expect(page.get_by_test_id("lesson-list")).to_be_hidden()
        # No list items must exist in the DOM at all.
        expect(page.get_by_test_id("lesson-list-item")).to_have_count(0)
    finally:
        ctx.close()


def test_logged_out_lessons_path_redirects_to_auth(browser: Browser, live_server: str) -> None:
    """A logged-out deep link to /lessons shows the auth form, not the list."""
    ctx, page = _fresh_page(browser)
    try:
        page.goto(live_server + "/lessons")
        expect(page.get_by_test_id("auth-gate")).to_be_visible()
        expect(page.get_by_test_id("login-form")).to_be_visible()
        expect(page.locator("#lesson-list-section")).to_be_hidden()
        expect(page.get_by_test_id("lesson-list-item")).to_have_count(0)
    finally:
        ctx.close()


def test_logged_out_lesson_deep_link_redirects_to_auth(browser: Browser, live_server: str) -> None:
    """A logged-out deep link to a lesson shows the auth form, leaking no content."""
    ctx, page = _fresh_page(browser)
    try:
        page.goto(f"{live_server}/?lesson={_REAL_SLUG}")
        expect(page.get_by_test_id("auth-gate")).to_be_visible()
        expect(page.get_by_test_id("login-form")).to_be_visible()

        # The lesson/exercise sections must stay hidden — no title leaks.
        expect(page.locator("#lesson-section")).to_be_hidden()
        expect(page.locator("#exercise-section")).to_be_hidden()
        # The lesson title must NOT contain the real lesson's text.
        expect(page.get_by_test_id("lesson-title")).not_to_contain_text(_REAL_LESSON_TITLE_EN)
    finally:
        ctx.close()


# ── 2. Logged-in path: content appears; logout returns to the gate ──────────


def test_login_then_lessons_list_appears(
    browser: Browser, live_server: str, seeded_user: SeededUser
) -> None:
    """With a valid token, the lessons-list view renders and the gate is hidden."""
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(live_server + "/lessons")
        page.wait_for_selector("[data-testid='lesson-list-item']")

        expect(page.get_by_test_id("auth-gate")).to_be_hidden()
        expect(page.get_by_test_id("lesson-list")).to_be_visible()
        # The logged-in chrome shows the account + a logout control.
        expect(page.get_by_test_id("logout-btn")).to_be_visible()
    finally:
        ctx.close()


def test_logout_returns_to_auth_form(
    browser: Browser, live_server: str, seeded_user: SeededUser
) -> None:
    """Clicking logout drops the token and returns the user to the auth form."""
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(live_server + "/lessons")
        page.wait_for_selector("[data-testid='lesson-list-item']")

        page.get_by_test_id("logout-btn").click()

        # Back to the gate; content gone.
        expect(page.get_by_test_id("auth-gate")).to_be_visible()
        expect(page.get_by_test_id("login-form")).to_be_visible()
        expect(page.locator("#lesson-list-section")).to_be_hidden()
    finally:
        ctx.close()


# ── 3. Auth-gate sub-state exclusivity ──────────────────────────────────────


def test_login_form_starts_with_hidden_class(browser: Browser, live_server: str) -> None:
    """login-form must carry its own 'hidden' class in the HTML on load.

    The gate's JS reveals exactly one sub-form via showLoginForm(); the element's
    own class must start hidden so no path exposes register/confirm-pending
    unexpectedly. Asserted on the class attribute directly, not effective
    visibility, so the test is sensitive to the HTML default.
    """
    ctx, page = _fresh_page(browser)
    try:
        page.goto(live_server + "/")
        # On load the gate is shown and the login form revealed; the register and
        # confirm-pending sub-states must remain hidden.
        expect(page.get_by_test_id("login-form")).to_be_visible()
        expect(page.get_by_test_id("register-form")).to_be_hidden()
        expect(page.get_by_test_id("confirm-pending")).to_be_hidden()
    finally:
        ctx.close()


def test_switch_to_register_shows_only_register_form(browser: Browser, live_server: str) -> None:
    """Clicking 'Register' on the gate shows exactly the register sub-form."""
    ctx, page = _fresh_page(browser)
    try:
        page.goto(live_server + "/")
        page.get_by_test_id("show-register").click()

        expect(page.get_by_test_id("register-form")).to_be_visible()
        expect(page.get_by_test_id("login-form")).to_be_hidden()
        expect(page.get_by_test_id("confirm-pending")).to_be_hidden()
    finally:
        ctx.close()


# ── 4. Authenticated section exclusivity + locale-pick correctness ──────────


def test_lesson_view_hides_list_section(
    browser: Browser, live_server: str, seeded_user: SeededUser
) -> None:
    """On a lesson URL (authenticated) the lesson-list section must be hidden."""
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_REAL_SLUG}")
        expect(page.get_by_test_id("lesson-title")).not_to_have_text("Loading…")

        expect(page.locator("#lesson-list-section")).to_be_hidden()
        expect(page.locator("#lesson-section")).to_be_visible()
        expect(page.locator("#exercise-section")).to_be_visible()
    finally:
        ctx.close()


def test_lesson_title_is_localized_string_not_object(
    browser: Browser, live_server: str, seeded_user: SeededUser
) -> None:
    """The lesson title must be the locale-picked string, not '[object Object]'."""
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_REAL_SLUG}")
        lesson_title = page.get_by_test_id("lesson-title")
        expect(lesson_title).not_to_have_text("Loading…")
        expect(lesson_title).not_to_contain_text("[object Object]")
        expect(lesson_title).to_have_text(_REAL_LESSON_TITLE_EN)
    finally:
        ctx.close()


def test_exercise_title_is_localized_string_not_object(
    browser: Browser, live_server: str, seeded_user: SeededUser
) -> None:
    """The exercise title must be the locale-picked string, not '[object Object]'."""
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_REAL_SLUG}")
        exercise_title = page.get_by_test_id("exercise-title")
        expect(exercise_title).not_to_have_text("")
        expect(exercise_title).not_to_contain_text("[object Object]")
        expect(exercise_title).to_have_text(_REAL_EXERCISE_TITLE_EN)
    finally:
        ctx.close()


# ── Screenshot for human verification ───────────────────────────────────────


def test_fe_fix_screenshot(browser: Browser, live_server: str, seeded_user: SeededUser) -> None:
    """Capture a screenshot of the authenticated lesson page for eyeball checks."""
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_REAL_SLUG}")
        expect(page.get_by_test_id("lesson-title")).not_to_have_text("Loading…")
        expect(page.get_by_test_id("lesson-title")).not_to_contain_text("[object Object]")
        expect(page.get_by_test_id("exercise-title")).not_to_contain_text("[object Object]")
        expect(page.locator("#lesson-list-section")).to_be_hidden()
        expect(page.get_by_test_id("auth-gate")).to_be_hidden()

        page.screenshot(path="/tmp/fe_fix.png", full_page=True)
    finally:
        ctx.close()
