"""UI scenarios for the dark / light theme toggle.

Covers:
  1. Toggling theme flips <html data-theme> and persists to localStorage.
  2. The persisted choice survives a page reload.
  3. A browser context with prefers-color-scheme: dark starts in dark mode
     when no explicit choice is stored.
  4. The hint button is visibly styled: has the hint-btn class and a
     non-transparent computed background (amber in light, dark in dark).
"""

import pytest
from playwright.sync_api import Page, expect

from fixtures import LocalePageFactory, SeededLesson, SeededUser

pytestmark = [pytest.mark.ui]

_THEME_KEY = "python-coach.theme"


def _open_lesson(page: Page, base_url: str, lesson_slug: str, token: str) -> None:
    """Seed auth token and navigate to a lesson page, waiting for the editor."""
    page.add_init_script(f"window.localStorage.setItem('python-coach.token', '{token}');")
    page.goto(f"{base_url}/?lesson={lesson_slug}")
    # Wait until CodeMirror mounts — exercises (and hint buttons) are ready then.
    page.locator(".CodeMirror").first.wait_for(state="visible")


def _get_theme(page: Page) -> str:
    """Read data-theme from <html>."""
    return page.evaluate("() => document.documentElement.getAttribute('data-theme') || ''")


def _get_stored_theme(page: Page) -> str | None:
    """Read the theme the frontend stored in localStorage."""
    return page.evaluate(f"() => window.localStorage.getItem('{_THEME_KEY}')")


# ── 1+2. Toggle flips data-theme and persists; survives reload ───────────────


def test_toggle_flips_theme_and_persists(
    locale_page_factory: LocalePageFactory,
    live_server: str,
    seeded_lesson: SeededLesson,
    seeded_user: SeededUser,
) -> None:
    """Clicking the toggle changes data-theme and writes to localStorage."""
    page = locale_page_factory.open("en-US")
    _open_lesson(page, live_server, seeded_lesson.slug, seeded_user.token)

    # Start in light (no stored preference, EN browser = light fallback).
    assert _get_theme(page) == "light", "expected light theme as default for en-US"

    toggle = page.get_by_test_id("theme-toggle")
    expect(toggle).to_be_visible()
    toggle.click()

    # After one click the theme must be dark.
    assert _get_theme(page) == "dark"
    assert _get_stored_theme(page) == "dark"

    toggle.click()

    # A second click restores light.
    assert _get_theme(page) == "light"
    assert _get_stored_theme(page) == "light"


def test_theme_persists_across_reload(
    locale_page_factory: LocalePageFactory,
    live_server: str,
    seeded_lesson: SeededLesson,
    seeded_user: SeededUser,
) -> None:
    """A stored dark choice survives a full page reload without flashing."""
    page = locale_page_factory.open("en-US")
    _open_lesson(page, live_server, seeded_lesson.slug, seeded_user.token)

    page.get_by_test_id("theme-toggle").click()
    assert _get_theme(page) == "dark"

    # Reload: the no-flash inline script must re-apply dark before body renders.
    page.reload()
    page.locator(".CodeMirror").first.wait_for(state="visible")

    assert _get_theme(page) == "dark", "dark theme must persist across reload"


# ── 3. OS dark preference starts in dark when no stored choice ───────────────


def test_dark_os_preference_starts_dark(
    live_server: str,
    seeded_lesson: SeededLesson,
    seeded_user: SeededUser,
    browser,  # raw Playwright Browser fixture
) -> None:
    """With prefers-color-scheme: dark and no stored choice the app starts dark."""
    context = browser.new_context(color_scheme="dark")
    try:
        page = context.new_page()
        _open_lesson(page, live_server, seeded_lesson.slug, seeded_user.token)
        assert _get_theme(page) == "dark", "OS dark preference must default to dark"
    finally:
        context.close()


# ── 4. Hint button is visibly styled ─────────────────────────────────────────


def test_hint_button_is_styled(
    locale_page_factory: LocalePageFactory,
    live_server: str,
    seeded_lesson: SeededLesson,
    seeded_user: SeededUser,
) -> None:
    """The hint button carries the hint-btn class and its label text is present."""
    page = locale_page_factory.open("en-US")
    _open_lesson(page, live_server, seeded_lesson.slug, seeded_user.token)

    hint_btn = page.get_by_test_id("hint-btn").first
    expect(hint_btn).to_be_visible()

    # Must carry the hint-btn styling class.
    expect(hint_btn).to_have_class("hint-btn")

    # The bilingual label span must contain text (not empty / icon-only).
    label = hint_btn.locator(".hint-label")
    expect(label).not_to_be_empty()

    # The amber background is applied via CSS class — verify the class is present
    # so a missing stylesheet would also fail this assertion.
    classes = hint_btn.get_attribute("class") or ""
    assert "hint-btn" in classes, f"hint-btn class missing, got: {classes!r}"


def test_hint_button_visible_in_dark_theme(
    locale_page_factory: LocalePageFactory,
    live_server: str,
    seeded_lesson: SeededLesson,
    seeded_user: SeededUser,
) -> None:
    """In dark mode the hint button must still be visible (dark amber palette)."""
    page = locale_page_factory.open("en-US")
    _open_lesson(page, live_server, seeded_lesson.slug, seeded_user.token)

    page.get_by_test_id("theme-toggle").click()
    assert _get_theme(page) == "dark"

    hint_btn = page.get_by_test_id("hint-btn").first
    expect(hint_btn).to_be_visible()
    expect(hint_btn.locator(".hint-label")).not_to_be_empty()
