"""Regression tests for view-management and locale-pick correctness.

Guards two classes of bugs introduced by the auth refactor (app.js/auth.js split):

  1. Mutual exclusivity of content sections and auth-modal sub-states.
     Before the fix, `login-form` lacked `class="hidden"` in the HTML, meaning
     JS had to rely solely on the parent modal being hidden to suppress it.  A
     test that asserts the element's own CSS class (not parent visibility) would
     fail on the unfixed HTML but pass once the element starts hidden.

  2. Locale-picking for localised title fields.
     The exercise and lesson title fields carry `{en, ru}` objects from the API.
     Inserting such an object directly into the DOM produces `[object Object]`.
     Asserting the rendered text equals the expected locale string catches any
     future removal of the `pick()` call in the render path.

These tests run against the live uvicorn server; all navigation is logged-out
(no token seeded) except where a fixture adds one.  The `functions-first-class`
lesson slug is used for the screenshot and title assertions because it is a
real, published lesson in the shared dev DB that the CI server serves.
"""

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

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


# ── Section visibility on list view ─────────────────────────────────────────


def test_list_view_section_exclusivity(browser: Browser, live_server: str) -> None:
    """On /, the lesson-list section is visible; all other content sections are hidden.

    Guards against a regression where lesson/exercise sections would show
    simultaneously with the list section (or before JS populated the list).
    """
    ctx, page = _fresh_page(browser)
    try:
        page.goto(live_server + "/")
        # Wait until JS has populated the lesson list before asserting state.
        page.wait_for_selector("[data-testid='lesson-list-item']")

        # Exactly one content section must be visible.
        expect(page.get_by_test_id("lesson-list")).to_be_visible()
        expect(page.locator("#lesson-section")).to_be_hidden()
        expect(page.locator("#exercise-section")).to_be_hidden()
    finally:
        ctx.close()


def test_auth_modal_hidden_on_load(browser: Browser, live_server: str) -> None:
    """The auth modal must be hidden when the page first loads (logged out).

    Ensures the modal's own CSS class and its effective visibility are both
    correct — a double guard so neither the class nor a CSS specificity change
    can slip through undetected.
    """
    ctx, page = _fresh_page(browser)
    try:
        page.goto(live_server + "/")
        page.wait_for_selector("[data-testid='lesson-list-item']")

        modal = page.get_by_test_id("auth-modal")
        expect(modal).to_be_hidden()

        # Confirm the hidden CSS class is actually on the element itself, not
        # only inherited from a parent, so a future CSS change cannot silently
        # break this.
        modal_class = modal.get_attribute("class") or ""
        assert "hidden" in modal_class, (
            f"auth-modal must carry its own 'hidden' class on load; got: '{modal_class}'"
        )
    finally:
        ctx.close()


# ── Auth modal sub-state exclusivity ────────────────────────────────────────


def test_login_form_starts_with_hidden_class(browser: Browser, live_server: str) -> None:
    """login-form must start with the 'hidden' CSS class in its own class attribute.

    Before the fix, login-form had no class at all: it relied solely on the
    parent modal being hidden.  That means any code path that opened the modal
    without calling showLoginForm() would expose the form unexpectedly.  After
    the fix, the element's own class carries 'hidden' so the invariant holds
    regardless of parent visibility.

    This assertion checks the class attribute directly (not effective Playwright
    visibility, which folds in parent state) so the test is sensitive to the
    exact HTML defect described above.
    """
    ctx, page = _fresh_page(browser)
    try:
        page.goto(live_server + "/")
        page.wait_for_selector("[data-testid='lesson-list-item']")

        login_form_class = page.locator("#login-form").get_attribute("class") or ""
        assert "hidden" in login_form_class, (
            "login-form must carry 'hidden' in its own class attribute on load; "
            f"got: '{login_form_class}'.  "
            "Root cause: the element's initial class was missing in the HTML."
        )
    finally:
        ctx.close()


def test_opening_modal_shows_only_login_form(browser: Browser, live_server: str) -> None:
    """Clicking 'Log in' shows the modal with exactly one sub-form visible.

    Asserts that register-form and confirm-pending are hidden, and that only
    login-form is visible — the single-active-sub-form invariant.
    """
    ctx, page = _fresh_page(browser)
    try:
        page.goto(live_server + "/")
        page.wait_for_selector("[data-testid='lesson-list-item']")

        page.get_by_test_id("open-auth-btn").click()

        # Modal must be visible after clicking.
        expect(page.get_by_test_id("auth-modal")).to_be_visible()

        # Exactly one sub-form: login.
        expect(page.get_by_test_id("login-form")).to_be_visible()
        expect(page.get_by_test_id("register-form")).to_be_hidden()
        expect(page.get_by_test_id("confirm-pending")).to_be_hidden()
    finally:
        ctx.close()


# ── Lesson view: section exclusivity + locale-pick correctness ──────────────


def test_lesson_view_hides_list_section(browser: Browser, live_server: str) -> None:
    """On a lesson URL the lesson-list section must be hidden.

    Guards against a regression where both the list and the lesson/exercise
    sections would stack on screen simultaneously.
    """
    ctx, page = _fresh_page(browser)
    try:
        page.goto(f"{live_server}/?lesson={_REAL_SLUG}")
        # Wait until lesson title is populated before asserting section state.
        expect(page.get_by_test_id("lesson-title")).not_to_have_text("Loading…")

        expect(page.locator("#lesson-list-section")).to_be_hidden()
        expect(page.locator("#lesson-section")).to_be_visible()
        expect(page.locator("#exercise-section")).to_be_visible()
    finally:
        ctx.close()


def test_lesson_title_is_localized_string_not_object(
    browser: Browser, live_server: str
) -> None:
    """The lesson title must be the locale-picked string, not '[object Object]'.

    '[object Object]' appears when a {en, ru} LocalizedText object is inserted
    into the DOM without routing it through pick().  This test asserts the
    exact expected EN text so any such regression is caught immediately.
    """
    ctx, page = _fresh_page(browser)
    try:
        page.goto(f"{live_server}/?lesson={_REAL_SLUG}")
        lesson_title = page.get_by_test_id("lesson-title")
        # Wait for content to load, then assert the exact expected value.
        expect(lesson_title).not_to_have_text("Loading…")
        expect(lesson_title).not_to_contain_text("[object Object]")
        expect(lesson_title).to_have_text(_REAL_LESSON_TITLE_EN)
    finally:
        ctx.close()


def test_exercise_title_is_localized_string_not_object(
    browser: Browser, live_server: str
) -> None:
    """The exercise title must be the locale-picked string, not '[object Object]'.

    Same invariant as the lesson title: asserting the exact EN string catches
    any future removal of the pick() call in renderProse().
    """
    ctx, page = _fresh_page(browser)
    try:
        page.goto(f"{live_server}/?lesson={_REAL_SLUG}")
        exercise_title = page.get_by_test_id("exercise-title")
        # The CodeMirror editor mounts after the exercise loads; waiting on the
        # title is sufficient since both are set in the same renderProse() call.
        expect(exercise_title).not_to_have_text("")
        expect(exercise_title).not_to_contain_text("[object Object]")
        expect(exercise_title).to_have_text(_REAL_EXERCISE_TITLE_EN)
    finally:
        ctx.close()


# ── Screenshot for human verification ───────────────────────────────────────


def test_fe_fix_screenshot(browser: Browser, live_server: str) -> None:
    """Capture a screenshot of the lesson page for eyeball verification.

    Saved to /tmp/fe_fix.png as requested.  The assertions here are the same
    invariants as the individual tests above, kept together so the screenshot
    reflects the verified state.
    """
    ctx, page = _fresh_page(browser)
    try:
        page.goto(f"{live_server}/?lesson={_REAL_SLUG}")
        expect(page.get_by_test_id("lesson-title")).not_to_have_text("Loading…")
        expect(page.get_by_test_id("lesson-title")).not_to_contain_text("[object Object]")
        expect(page.get_by_test_id("exercise-title")).not_to_contain_text("[object Object]")
        expect(page.locator("#lesson-list-section")).to_be_hidden()
        expect(page.get_by_test_id("auth-modal")).to_be_hidden()

        page.screenshot(path="/tmp/fe_fix.png", full_page=True)
    finally:
        ctx.close()
