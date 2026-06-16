"""Page object for the single-page lesson UI.

POM contract (per .claude/references/qa/pom-patterns.md): this object *acts* —
it navigates, types a solution into the CodeMirror editor, and clicks Check. It
exposes locators for the scenario to assert on, but contains no `expect(...)`
itself. Selectors are testid-first.
"""

from playwright.sync_api import Locator, Page, expect


class LessonPage:
    """Drives the lesson page: load -> type solution -> Check -> read results."""

    def __init__(
        self, page: Page, base_url: str, lesson_slug: str, token: str | None = None
    ) -> None:
        self.page = page
        self._base_url = base_url
        self._lesson_slug = lesson_slug
        self._token = token

    # --- navigation -------------------------------------------------------

    def open(self) -> "LessonPage":
        """Navigate to the lesson by slug and wait until the editor is interactive."""
        # Submitting is gated behind login: seed the bearer token before the app
        # boots so the Check button is enabled (init script runs pre-navigation).
        if self._token is not None:
            self.page.add_init_script(
                f"window.localStorage.setItem('python-coach.token', '{self._token}');"
            )
        self.page.goto(f"{self._base_url}/?lesson={self._lesson_slug}")
        # The CodeMirror widget only renders after the exercise loads; waiting on
        # it (not a timeout) removes the navigation/first-interaction race.
        expect(self.exercise_title).not_to_have_text("")
        self.page.locator(".CodeMirror").wait_for(state="visible")
        return self

    # --- actions ----------------------------------------------------------

    def set_solution(self, code: str) -> "LessonPage":
        """Replace the editor contents with `code` via the CodeMirror widget."""
        editor = self.page.locator(".CodeMirror")
        editor.click()
        # Select-all then type: CodeMirror's real textarea is hidden, so we drive
        # it through the widget the way a user would (cross-platform select-all).
        self.page.keyboard.press("ControlOrMeta+A")
        self.page.keyboard.press("Delete")
        self.page.keyboard.type(code)
        return self

    def submit(self) -> "LessonPage":
        """Click Check and wait for the results panel to appear."""
        self.check_button.click()
        self.results_panel.wait_for(state="visible")
        return self

    # --- locators (for the scenario to assert on) -------------------------

    @property
    def lesson_title(self) -> Locator:
        return self.page.get_by_test_id("lesson-title")

    @property
    def exercise_title(self) -> Locator:
        return self.page.get_by_test_id("exercise-title")

    @property
    def check_button(self) -> Locator:
        return self.page.get_by_test_id("check-btn")

    @property
    def progress_badge(self) -> Locator:
        return self.page.get_by_test_id("progress-badge")

    @property
    def results_panel(self) -> Locator:
        return self.page.get_by_test_id("results-panel")

    @property
    def results_summary(self) -> Locator:
        return self.page.get_by_test_id("results-summary")

    @property
    def result_items(self) -> Locator:
        return self.page.get_by_test_id("result-item")

    @property
    def results_error(self) -> Locator:
        return self.page.get_by_test_id("results-error")

    def result_item_by_outcome(self, outcome: str) -> Locator:
        """Result rows tagged with a given pytest outcome (passed/failed/error).

        The outcome lives on the row's own `data-outcome` attribute, so we narrow
        the testid-anchored row locator by that attribute rather than a child.
        """
        return self.result_items.and_(self.page.locator(f"[data-outcome='{outcome}']"))
