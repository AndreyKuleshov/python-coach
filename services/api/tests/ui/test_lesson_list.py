"""UI scenarios for the curriculum lesson-list page.

Verifies: list renders at /, EN/RU switching retitles items instantly, clicking
an item opens the lesson view, and the back link returns to the list.
Screenshots are saved next to this file for the verification report.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.ui]

_SCREENSHOT_DIR = Path(__file__).parent

# Expected titles for the two published decorator lessons (both locales).
_EN_HEADING = "Lessons"
_RU_HEADING = "Уроки"
_BASICS_EN = "Decorators: the basics"
_BASICS_RU = "Декораторы: основы"


def test_list_shows_published_lessons(page: Page, live_server: str) -> None:
    """The list view renders published lessons; the placeholder is absent."""
    page.goto(live_server + "/")
    # Wait for at least one list item to appear (JS fetch may take a moment).
    page.wait_for_selector("[data-testid='lesson-list-item']")

    list_el = page.get_by_test_id("lesson-list")
    expect(list_el).to_be_visible()

    # At least one published lesson must be present — don't pin the total count
    # so the test doesn't break when the methodist adds more published lessons.
    items = page.get_by_test_id("lesson-list-item")
    assert items.count() >= 1

    # Both known published fixtures must be individually visible.
    expect(page.locator("[data-slug='decorators-basics']")).to_have_count(1)
    expect(page.locator("[data-slug='decorators-advanced']")).to_have_count(1)

    # The unpublished placeholder must not appear in the list.
    expect(page.locator("[data-slug='placeholder-intro']")).to_have_count(0)

    # Heading defaults to EN.
    expect(page.get_by_test_id("list-heading")).to_have_text(_EN_HEADING)

    # Screenshot for the verification report.
    page.screenshot(path=str(_SCREENSHOT_DIR / "screenshot_list_en.png"))


def test_list_locale_switch_updates_titles(page: Page, live_server: str) -> None:
    """Switching to RU instantly re-renders the list heading and item titles."""
    page.goto(live_server + "/")
    page.wait_for_selector("[data-testid='lesson-list-item']")

    # Switch to Russian.
    page.get_by_test_id("lang-ru").click()
    expect(page.get_by_test_id("list-heading")).to_have_text(_RU_HEADING)

    # Locate the basics row by slug, not by position — order may change as
    # more lessons are published.
    basics_row = page.locator("[data-slug='decorators-basics']")
    expect(basics_row).to_contain_text(_BASICS_RU)

    page.screenshot(path=str(_SCREENSHOT_DIR / "screenshot_list_ru.png"))

    # Switch back to EN.
    page.get_by_test_id("lang-en").click()
    expect(page.get_by_test_id("list-heading")).to_have_text(_EN_HEADING)
    expect(basics_row).to_contain_text(_BASICS_EN)

    page.screenshot(path=str(_SCREENSHOT_DIR / "screenshot_list_en_back.png"))


def test_list_item_slug_attribute(page: Page, live_server: str) -> None:
    """Each list item exposes its slug via data-slug for QA tooling."""
    page.goto(live_server + "/")
    page.wait_for_selector("[data-testid='lesson-list-item']")

    items = page.get_by_test_id("lesson-list-item").all()
    for item in items:
        slug = item.get_attribute("data-slug")
        assert slug, f"data-slug missing on list item: {item.inner_html()}"


def test_clicking_list_item_opens_lesson(page: Page, live_server: str) -> None:
    """Clicking a lesson list item navigates to the lesson view."""
    page.goto(live_server + "/")
    page.wait_for_selector("[data-testid='lesson-list-item']")

    # Click the first item's link.
    page.get_by_test_id("lesson-list-item").first.locator("a").click()

    # The lesson view must appear with the back link and lesson title.
    expect(page.get_by_test_id("back-to-lessons")).to_be_visible()
    expect(page.get_by_test_id("lesson-title")).not_to_have_text("Loading…")
    expect(page.get_by_test_id("lesson-title")).not_to_have_text("")

    page.screenshot(path=str(_SCREENSHOT_DIR / "screenshot_lesson_view.png"))


def test_back_link_returns_to_list(page: Page, live_server: str) -> None:
    """The '← Back to lessons' link in the lesson view returns to the list."""
    # Navigate directly to one of the real lessons.
    page.goto(f"{live_server}/?lesson=decorators-basics")
    expect(page.get_by_test_id("back-to-lessons")).to_be_visible()

    page.get_by_test_id("back-to-lessons").click()

    # We should be back on the list view.
    page.wait_for_selector("[data-testid='lesson-list-item']")
    expect(page.get_by_test_id("lesson-list")).to_be_visible()
    expect(page.get_by_test_id("list-heading")).to_be_visible()

    page.screenshot(path=str(_SCREENSHOT_DIR / "screenshot_back_to_list.png"))
