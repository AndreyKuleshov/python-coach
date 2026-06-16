"""Page objects for the bilingual (EN/RU) chrome shared by both views.

The language switcher lives in the page header and is identical on the list
view and the lesson view, so a single component object drives it for both. Per
the POM contract (.claude/references/qa/pom-patterns.md) these objects *act* —
they navigate and click the EN/RU buttons and read the persisted locale — but
hold no `expect(...)`; assertions live in the scenario files.

Selectors are testid-first: `lang-switch` / `lang-en` / `lang-ru` plus the
existing prose/heading testids the views already expose.
"""

from playwright.sync_api import Locator, Page

# Where the frontend persists a manual locale choice (see static/app.js).
_LOCALE_STORAGE_KEY = "python-coach.locale"


class LangSwitch:
    """The EN/RU toggle in the header — present on both list and lesson views."""

    def __init__(self, page: Page) -> None:
        self.page = page

    @property
    def root(self) -> Locator:
        return self.page.get_by_test_id("lang-switch")

    @property
    def en_button(self) -> Locator:
        return self.page.get_by_test_id("lang-en")

    @property
    def ru_button(self) -> Locator:
        return self.page.get_by_test_id("lang-ru")

    def to_en(self) -> "LangSwitch":
        """Click the EN button (instant client-side switch, no reload)."""
        self.en_button.click()
        return self

    def to_ru(self) -> "LangSwitch":
        """Click the RU button (instant client-side switch, no reload)."""
        self.ru_button.click()
        return self

    def persisted_locale(self) -> str | None:
        """Read the locale the frontend stored in localStorage (None if unset)."""
        return self.page.evaluate("key => window.localStorage.getItem(key)", _LOCALE_STORAGE_KEY)


class ListView:
    """The authenticated lessons-list view (/lessons): heading, items, switcher.

    The list is gated behind login, so the POM seeds a bearer token into
    localStorage before navigation (init script runs pre-navigation).
    """

    def __init__(self, page: Page, base_url: str, token: str | None = None) -> None:
        self.page = page
        self._base_url = base_url
        self._token = token
        self.lang = LangSwitch(page)

    def open(self) -> "ListView":
        """Navigate to /lessons (authenticated) and wait for the list to populate."""
        if self._token is not None:
            self.page.add_init_script(
                f"window.localStorage.setItem('python-coach.token', '{self._token}');"
            )
        self.page.goto(f"{self._base_url}/lessons")
        # The list is filled by a fetch; wait on the first item rather than a
        # timeout so the navigation/first-paint race is removed.
        self.first_item.wait_for(state="visible")
        return self

    def reload(self) -> "ListView":
        """Reload the page and wait for the list to re-populate (persistence check)."""
        self.page.reload()
        self.first_item.wait_for(state="visible")
        return self

    @property
    def heading(self) -> Locator:
        return self.page.get_by_test_id("list-heading")

    @property
    def items(self) -> Locator:
        return self.page.get_by_test_id("lesson-list-item")

    @property
    def first_item(self) -> Locator:
        return self.items.first

    def item_by_slug(self, slug: str) -> Locator:
        """A list row located by its stable data-slug, not by position.

        Uses the row's own data-slug (present on every row, locked or not)
        rather than the link href — locked rows carry no link, so an href-based
        filter would miss them.
        """
        return self.page.locator(f"[data-testid='lesson-list-item'][data-slug='{slug}']")


class LessonView:
    """The lesson view (?lesson=<slug>): prose, chrome strings, switcher, editor.

    The lesson is gated behind login, so the POM seeds a bearer token into
    localStorage before navigation (init script runs pre-navigation).
    """

    def __init__(
        self, page: Page, base_url: str, lesson_slug: str, token: str | None = None
    ) -> None:
        self.page = page
        self._base_url = base_url
        self._lesson_slug = lesson_slug
        self._token = token
        self.lang = LangSwitch(page)

    def open(self) -> "LessonView":
        """Navigate to the lesson by slug (authenticated) and wait for the editor."""
        if self._token is not None:
            self.page.add_init_script(
                f"window.localStorage.setItem('python-coach.token', '{self._token}');"
            )
        self.page.goto(f"{self._base_url}/?lesson={self._lesson_slug}")
        # The CodeMirror widget only mounts after the exercise loads; waiting on
        # the populated title + widget removes the first-interaction race.
        self.editor.wait_for(state="visible")
        return self

    def reload(self) -> "LessonView":
        """Reload and wait for the editor to re-mount (persistence check)."""
        self.page.reload()
        self.editor.wait_for(state="visible")
        return self

    def type_into_editor(self, text: str) -> "LessonView":
        """Append `text` into the CodeMirror editor (drives the real widget)."""
        self.editor.click()
        self.page.keyboard.type(text)
        return self

    def editor_text(self) -> str:
        """Current editor contents, read from the live CodeMirror instance."""
        return self.page.evaluate(
            "() => document.querySelector('.CodeMirror').CodeMirror.getValue()"
        )

    @property
    def editor(self) -> Locator:
        return self.page.locator(".CodeMirror")

    @property
    def lesson_title(self) -> Locator:
        return self.page.get_by_test_id("lesson-title")

    @property
    def exercise_title(self) -> Locator:
        return self.page.get_by_test_id("exercise-title")

    @property
    def editor_label(self) -> Locator:
        return self.page.get_by_test_id("editor-label")

    @property
    def check_button(self) -> Locator:
        return self.page.get_by_test_id("check-btn")

    @property
    def back_link(self) -> Locator:
        return self.page.get_by_test_id("back-to-lessons")
