"""UI scenarios for the lesson page: open -> type solution -> Check -> results.

These drive a real browser against a live server and the real Docker sandbox.
Assertions live here (web-first `expect`), never in the page object.
"""

import pytest
from playwright.sync_api import expect

from lesson_page import LessonPage

pytestmark = [pytest.mark.ui]

_CORRECT = "def answer():\n    return 42\n"
_WRONG = "def answer():\n    return 7\n"


def test_passing_submission_shows_all_green(lesson_page: LessonPage) -> None:
    """A correct solution renders a passing summary and a passed result row."""
    lesson_page.open().set_solution(_CORRECT).submit()

    expect(lesson_page.results_panel).to_be_visible()
    expect(lesson_page.results_summary).to_contain_text("all passed")
    expect(lesson_page.result_item_by_outcome("passed")).to_have_count(1)
    expect(lesson_page.result_item_by_outcome("failed")).to_have_count(0)
    expect(lesson_page.results_error).to_be_hidden()
    expect(lesson_page.progress_badge).to_contain_text("solved")


def test_failing_submission_surfaces_the_assertion(lesson_page: LessonPage) -> None:
    """A wrong solution renders a failed result row carrying the assertion text."""
    lesson_page.open().set_solution(_WRONG).submit()

    expect(lesson_page.results_panel).to_be_visible()
    failed_row = lesson_page.result_item_by_outcome("failed")
    expect(failed_row).to_have_count(1)
    # The seeded test's custom assertion message must reach the panel verbatim.
    expect(failed_row).to_contain_text("answer() must return 42")
    expect(lesson_page.results_summary).to_contain_text("0/1 passed")
