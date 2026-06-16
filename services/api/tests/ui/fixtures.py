"""Shared type definitions for the UI test suite.

These dataclasses are imported by both ``tests/ui/conftest.py`` (fixtures that
produce them) and ``tests/ui/test_lang_switch.py`` (scenarios that annotate
fixture parameters with them). Keeping definitions here — rather than in
``conftest.py`` — avoids a circular import: pytest adds ``tests/ui/`` to
``sys.path`` when loading ``conftest.py``, so ``from conftest import …`` inside
conftest itself resolves back to the same file.
"""

from dataclasses import dataclass

from playwright.sync_api import Browser, BrowserContext, Page


@dataclass(frozen=True, slots=True)
class SeededLesson:
    """Slug + exercise id of the lesson seeded for the UI Playwright flow."""

    slug: str
    exercise_id: int


@dataclass(frozen=True, slots=True)
class LocalePageFactory:
    """Opens a fresh, isolated browser context whose navigator.language is set.

    Default-locale resolution depends on (a) navigator.language and (b) an empty
    localStorage. A brand-new context gives both deterministically, and one
    context per call keeps tests isolated under pytest-xdist (no shared storage).
    """

    browser: Browser
    _contexts: list[BrowserContext]

    def open(self, locale: str) -> Page:
        """A new page in a new context with `locale` driving navigator.language."""
        context = self.browser.new_context(locale=locale)
        self._contexts.append(context)
        return context.new_page()
