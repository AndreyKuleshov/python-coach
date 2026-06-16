"""UI scenarios for the EN/RU language switcher, on BOTH views.

Covers the three behaviours of the bilingual frontend (CONTEXT.md "bilingual
content"):

  1. Default-locale resolution from navigator.language (RU for ru-RU, EN
     fallback for an unsupported/en-US locale). Driven via a real browser
     context `locale=...`, not by mocking navigator.
  2. Instant EN<->RU toggling that swaps BOTH the lesson/list prose AND the UI
     chrome strings (heading, button label, editor label) with no reload — and,
     on the lesson view, without losing the learner's editor input.
  3. The chosen locale persists in localStorage and survives a reload and a
     fresh navigation, overriding the browser default.

Selectors are testid-first; assertions are web-first `expect`; the POMs only
act. One isolated browser context per page so localStorage never leaks across
tests (safe under pytest-xdist).
"""

import pytest
from playwright.sync_api import expect

from fixtures import LocalePageFactory, SeededLesson, SeededUser
from i18n_page import LessonView, ListView

pytestmark = [pytest.mark.ui]

# Chrome strings (from static/app.js UI catalog) — the i18n contract under test.
_LIST_HEADING = {"en": "Lessons", "ru": "Уроки"}
_BACK_LINK = {"en": "Back to lessons", "ru": "К списку уроков"}
_EDITOR_LABEL = {"en": "Your solution", "ru": "Ваше решение"}
_CHECK = {"en": "Check", "ru": "Проверить"}

# Prose of the session-seeded UI lesson (see ui/conftest.py::_seed).
_LESSON_TITLE = {"en": "UI seeded lesson", "ru": "UI урок"}
_EXERCISE_TITLE = {"en": "Return 42", "ru": "Верните 42"}

# Prose of a real published list fixture, located by stable slug.
_BASICS_SLUG = "decorators-basics"
_BASICS_TITLE = {"en": "Decorators: the basics", "ru": "Декораторы: основы"}


# ── 1. Default-locale resolution from navigator.language ────────────────────


@pytest.mark.parametrize(
    ("browser_locale", "expected"),
    [("ru-RU", "ru"), ("en-US", "en"), ("fr-FR", "en")],
    ids=["ru-RU->ru", "en-US->en", "unsupported->en-fallback"],
)
def test_list_default_locale_follows_browser(
    locale_page_factory: LocalePageFactory,
    live_server: str,
    seeded_user: SeededUser,
    browser_locale: str,
    expected: str,
) -> None:
    """On the list view, the initial locale follows navigator.language (EN fallback)."""
    page = locale_page_factory.open(browser_locale)
    view = ListView(page, base_url=live_server, token=seeded_user.token).open()

    expect(view.heading).to_have_text(_LIST_HEADING[expected])
    expect(view.item_by_slug(_BASICS_SLUG)).to_contain_text(_BASICS_TITLE[expected])


@pytest.mark.parametrize(
    ("browser_locale", "expected"),
    [("ru-RU", "ru"), ("en-US", "en"), ("fr-FR", "en")],
    ids=["ru-RU->ru", "en-US->en", "unsupported->en-fallback"],
)
def test_lesson_default_locale_follows_browser(
    locale_page_factory: LocalePageFactory,
    live_server: str,
    seeded_lesson: SeededLesson,
    seeded_user: SeededUser,
    browser_locale: str,
    expected: str,
) -> None:
    """On the lesson view, the initial locale follows navigator.language (EN fallback)."""
    page = locale_page_factory.open(browser_locale)
    view = LessonView(
        page, base_url=live_server, lesson_slug=seeded_lesson.slug, token=seeded_user.token
    ).open()

    expect(view.lesson_title).to_have_text(_LESSON_TITLE[expected])
    expect(view.editor_label).to_have_text(_EDITOR_LABEL[expected])


# ── 2. Instant toggle swaps prose AND chrome, no reload ─────────────────────


def test_list_toggle_swaps_prose_and_chrome(
    locale_page_factory: LocalePageFactory, live_server: str, seeded_user: SeededUser
) -> None:
    """EN->RU->EN on the list view retitles items AND the heading instantly."""
    page = locale_page_factory.open("en-US")
    view = ListView(page, base_url=live_server, token=seeded_user.token).open()
    basics = view.item_by_slug(_BASICS_SLUG)

    expect(view.heading).to_have_text(_LIST_HEADING["en"])
    expect(basics).to_contain_text(_BASICS_TITLE["en"])

    view.lang.to_ru()
    expect(view.heading).to_have_text(_LIST_HEADING["ru"])
    expect(basics).to_contain_text(_BASICS_TITLE["ru"])

    view.lang.to_en()
    expect(view.heading).to_have_text(_LIST_HEADING["en"])
    expect(basics).to_contain_text(_BASICS_TITLE["en"])


def test_lesson_toggle_swaps_prose_and_chrome(
    locale_page_factory: LocalePageFactory,
    live_server: str,
    seeded_lesson: SeededLesson,
    seeded_user: SeededUser,
) -> None:
    """EN->RU on the lesson view swaps lesson prose AND every chrome string."""
    page = locale_page_factory.open("en-US")
    view = LessonView(
        page, base_url=live_server, lesson_slug=seeded_lesson.slug, token=seeded_user.token
    ).open()

    # Start in EN: prose + chrome.
    expect(view.lesson_title).to_have_text(_LESSON_TITLE["en"])
    expect(view.exercise_title).to_have_text(_EXERCISE_TITLE["en"])
    expect(view.editor_label).to_have_text(_EDITOR_LABEL["en"])
    expect(view.check_button).to_have_text(_CHECK["en"])
    expect(view.back_link).to_contain_text(_BACK_LINK["en"])

    view.lang.to_ru()

    # Everything flips to RU at once, no reload.
    expect(view.lesson_title).to_have_text(_LESSON_TITLE["ru"])
    expect(view.exercise_title).to_have_text(_EXERCISE_TITLE["ru"])
    expect(view.editor_label).to_have_text(_EDITOR_LABEL["ru"])
    expect(view.check_button).to_have_text(_CHECK["ru"])
    expect(view.back_link).to_contain_text(_BACK_LINK["ru"])


def test_lesson_toggle_keeps_editor_input(
    locale_page_factory: LocalePageFactory,
    live_server: str,
    seeded_lesson: SeededLesson,
    seeded_user: SeededUser,
) -> None:
    """A locale switch must not rebuild the editor or drop the learner's edits."""
    page = locale_page_factory.open("en-US")
    view = LessonView(
        page, base_url=live_server, lesson_slug=seeded_lesson.slug, token=seeded_user.token
    ).open()

    sentinel = "# my-work-in-progress\n"
    view.type_into_editor(sentinel)
    view.lang.to_ru()

    # The chrome flipped to RU (confirming the switch happened)...
    expect(view.editor_label).to_have_text(_EDITOR_LABEL["ru"])
    # ...and the in-progress code is still in the editor.
    assert sentinel.strip() in view.editor_text()


# ── 3. Persistence in localStorage, surviving reload + fresh navigation ─────


def test_choice_persists_across_reload_overriding_browser(
    locale_page_factory: LocalePageFactory, live_server: str, seeded_user: SeededUser
) -> None:
    """A manual RU choice in an EN browser persists in localStorage and survives reload."""
    # Browser default is EN; the user manually picks RU.
    page = locale_page_factory.open("en-US")
    view = ListView(page, base_url=live_server, token=seeded_user.token).open()
    expect(view.heading).to_have_text(_LIST_HEADING["en"])

    view.lang.to_ru()
    expect(view.heading).to_have_text(_LIST_HEADING["ru"])
    assert view.lang.persisted_locale() == "ru"

    # Reload: the persisted RU choice wins over the EN browser default.
    view.reload()
    expect(view.heading).to_have_text(_LIST_HEADING["ru"])


def test_choice_survives_fresh_navigation_to_lesson(
    locale_page_factory: LocalePageFactory,
    live_server: str,
    seeded_lesson: SeededLesson,
    seeded_user: SeededUser,
) -> None:
    """A RU choice on the list view carries to a fresh navigation into a lesson.

    Same context (so localStorage carries), EN browser default: the stored RU
    choice must still win after navigating to a different page.
    """
    page = locale_page_factory.open("en-US")
    list_view = ListView(page, base_url=live_server, token=seeded_user.token).open()
    list_view.lang.to_ru()
    assert list_view.lang.persisted_locale() == "ru"

    # Fresh navigation (not a reload) to the lesson view, same storage.
    lesson_view = LessonView(
        page, base_url=live_server, lesson_slug=seeded_lesson.slug, token=seeded_user.token
    ).open()
    expect(lesson_view.lesson_title).to_have_text(_LESSON_TITLE["ru"])
    expect(lesson_view.editor_label).to_have_text(_EDITOR_LABEL["ru"])
