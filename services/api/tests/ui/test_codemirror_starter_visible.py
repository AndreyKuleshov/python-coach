"""UI test for Bug 0006 — CodeMirror starter code must be visible on load.

Asserts that the rendered DOM of the first exercise's CodeMirror editor
contains the expected starter-code token immediately after page load,
*before* any click or focus interaction.

Intentionally avoids CodeMirror.getValue() — that API returns the internal
value even when the editor has never been painted (it would not catch this
visual bug). Instead, the test reads the text content of .CodeMirror-code,
which is only populated once CodeMirror has performed a layout pass and
actually rendered the lines into the DOM.

Uses the session-scoped ``seeded_lesson`` fixture (position=0, always the
first in the curriculum and therefore always unlocked for a fresh user)
rather than a hard-coded fixture lesson slug.  A fixed fixture slug such as
``functions-first-class`` (position=1) becomes locked when another test's
session fixture inserts a lesson at position=0 before it, which caused this
test to receive a 403 and time out waiting for the CodeMirror widget.
"""

import pytest
from playwright.sync_api import Browser, expect

from fixtures import SeededLesson, SeededUser

pytestmark = [pytest.mark.ui]

# Token that must appear in the rendered CodeMirror DOM on load.
# The seeded_lesson fixture seeds starter_code="def answer():\n    return 0\n",
# so "answer" is a reliable token that exists only after a successful refresh.
_STARTER_TOKEN = "answer"


def _authed_page(browser: Browser, token: str):  # type: ignore[return]
    """Open a fresh browser context with the bearer token pre-seeded."""
    ctx = browser.new_context()
    page = ctx.new_page()
    page.add_init_script(f"window.localStorage.setItem('python-coach.token', '{token}');")
    return ctx, page


def test_starter_code_visible_on_load_without_click(
    browser: Browser,
    live_server: str,
    seeded_lesson: SeededLesson,
    seeded_user: SeededUser,
) -> None:
    """First exercise's starter code is painted in the DOM before any user interaction.

    We assert the rendered .CodeMirror-code text — not the internal editor
    value — so the test catches the "empty box until click" visual regression.
    The seeded_lesson is always position=0 (first in curriculum, always
    unlocked), so this test is immune to other session fixtures inserting
    earlier lessons.
    """
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={seeded_lesson.slug}")

        # Wait until the first CodeMirror widget is visible (editors mounted).
        first_cm = page.locator(".CodeMirror").first
        first_cm.wait_for(state="visible")

        # Give the requestAnimationFrame refresh time to fire.
        # 500 ms is generous; the rAF runs in the very next paint cycle.
        page.wait_for_timeout(500)

        # Assert the rendered code content — NOT getValue(). The .CodeMirror-code
        # element holds all rendered line divs; it is only populated after a
        # successful layout/refresh pass. Before the fix this element is empty.
        code_div = first_cm.locator(".CodeMirror-code")
        expect(code_div).to_contain_text(_STARTER_TOKEN)

        page.screenshot(path="/tmp/cm_fix.png", full_page=True)
    finally:
        ctx.close()
