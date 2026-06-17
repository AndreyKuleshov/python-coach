"""UI scenarios for the AI hint button + floating lesson-chat widget.

The live server runs in OFFLINE FAKE LLM mode (OPENAI_FAKE=true, set in the
``live_server`` fixture), so these drive a real browser and our real backend but
never touch OpenAI. The fake returns deterministic canned text, so we assert on
its known marker rather than model output.

Assertions live here (web-first `expect`), never in the page object.
"""

import pytest
from playwright.sync_api import expect

from lesson_page import LessonPage

pytestmark = [pytest.mark.ui]


def test_hint_button_reveals_a_hint(lesson_page: LessonPage) -> None:
    """Clicking Hint on an exercise reveals the hint text from our backend."""
    lesson_page.open()
    expect(lesson_page.hint_button()).to_be_visible()
    lesson_page.request_hint()
    # The offline fake returns a deterministic hint marker.
    expect(lesson_page.hint_text()).to_contain_text("offline mode")


def test_chat_widget_opens_and_answers(lesson_page: LessonPage) -> None:
    """The floating chat widget opens, accepts a pasted excerpt, and shows an answer."""
    lesson_page.open()
    expect(lesson_page.chat_toggle).to_be_visible()
    lesson_page.ask_chat("A generator yields values lazily instead of building a list.")
    expect(lesson_page.chat_answer).to_contain_text("offline mode")


def test_chat_close_button_hides_panel_and_toggle_reopens(lesson_page: LessonPage) -> None:
    """Close button collapses the panel; the toggle button re-expands it symmetrically.

    This was broken because .ai-chat-panel's display:flex overrode the generic
    .hidden { display:none } rule (equal specificity, later rule wins in CSS).
    The fix adds .ai-chat-panel.hidden { display:none } to raise specificity.
    """
    lesson_page.open()

    # Panel is initially hidden; open it via the toggle.
    expect(lesson_page.chat_panel).not_to_be_visible()
    lesson_page.chat_toggle.click()
    expect(lesson_page.chat_panel).to_be_visible()

    # Click Close — the panel must disappear.
    lesson_page.chat_close.click()
    expect(lesson_page.chat_panel).not_to_be_visible()

    # Toggle must re-open the panel (symmetry check).
    lesson_page.chat_toggle.click()
    expect(lesson_page.chat_panel).to_be_visible()
