"""Page object for the single-page lesson UI.

POM contract (per .claude/references/qa/pom-patterns.md): this object *acts* —
it navigates, types a solution into the CodeMirror editor, and clicks Check. It
exposes locators for the scenario to assert on, but contains no `expect(...)`
itself. Selectors are testid-first.

Updated for multi-exercise lessons: exercises are rendered as independent blocks
(data-testid="exercise-item"). The POM targets the *first* exercise block by
default so existing single-exercise tests keep passing without change. New
helpers let callers target a specific exercise by index or slug.
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
        """Navigate to the lesson by slug and wait until the first editor is interactive."""
        # Submitting is gated behind login: seed the bearer token before the app
        # boots so the Check button is enabled (init script runs pre-navigation).
        if self._token is not None:
            self.page.add_init_script(
                f"window.localStorage.setItem('python-coach.token', '{self._token}');"
            )
        self.page.goto(f"{self._base_url}/?lesson={self._lesson_slug}")
        # The CodeMirror widget only renders after exercises load; waiting on
        # it (not a timeout) removes the navigation/first-interaction race.
        expect(self.first_exercise_title).not_to_have_text("")
        self.page.locator(".CodeMirror").first.wait_for(state="visible")
        return self

    # --- actions ----------------------------------------------------------

    def set_solution(self, code: str, exercise_index: int = 0) -> "LessonPage":
        """Replace the editor contents with `code` for the exercise at `exercise_index`."""
        # Each exercise block has its own CodeMirror widget; nth(i) selects the right one.
        editor = self.page.locator(".CodeMirror").nth(exercise_index)
        editor.click()
        # Select-all then type: CodeMirror's real textarea is hidden, so we drive
        # it through the widget the way a user would (cross-platform select-all).
        self.page.keyboard.press("ControlOrMeta+A")
        self.page.keyboard.press("Delete")
        self.page.keyboard.type(code)
        return self

    def submit(self, exercise_index: int = 0) -> "LessonPage":
        """Click Check for the exercise at `exercise_index` and wait for results."""
        self.check_button(exercise_index).click()
        self.results_panel(exercise_index).wait_for(state="visible")
        return self

    # --- multi-exercise locators ------------------------------------------

    @property
    def exercise_items(self) -> Locator:
        """All exercise blocks on the page (ordered)."""
        return self.page.get_by_test_id("exercise-item")

    def exercise_item(self, index: int = 0) -> Locator:
        """A single exercise block by position (0-based)."""
        return self.exercise_items.nth(index)

    def exercise_item_by_slug(self, slug: str) -> Locator:
        """A single exercise block by its data-slug attribute."""
        return self.page.locator(f"[data-testid='exercise-item'][data-slug='{slug}']")

    @property
    def first_exercise_title(self) -> Locator:
        """The title of the first exercise block."""
        return self.page.get_by_test_id("exercise-item-title").first

    def check_button(self, exercise_index: int = 0) -> Locator:
        """The Check button for the exercise at `exercise_index`."""
        return self.exercise_item(exercise_index).get_by_test_id("check-btn")

    def results_panel(self, exercise_index: int = 0) -> Locator:
        """The results panel for the exercise at `exercise_index`."""
        return self.exercise_item(exercise_index).get_by_test_id("results-panel")

    def results_summary(self, exercise_index: int = 0) -> Locator:
        """The results summary span for the exercise at `exercise_index`."""
        return self.exercise_item(exercise_index).get_by_test_id("results-summary")

    def result_items(self, exercise_index: int = 0) -> Locator:
        """All result rows for the exercise at `exercise_index`."""
        return self.exercise_item(exercise_index).get_by_test_id("result-item")

    def results_error(self, exercise_index: int = 0) -> Locator:
        """The runner-error pre for the exercise at `exercise_index`."""
        return self.exercise_item(exercise_index).get_by_test_id("results-error")

    def solved_badge(self, exercise_index: int = 0) -> Locator:
        """The solved badge for the exercise at `exercise_index`."""
        return self.exercise_item(exercise_index).get_by_test_id("solved-badge")

    def result_item_by_outcome(self, outcome: str, exercise_index: int = 0) -> Locator:
        """Result rows tagged with a given pytest outcome (passed/failed/error).

        The outcome lives on the row's own `data-outcome` attribute, so we narrow
        the testid-anchored row locator by that attribute rather than a child.
        """
        return self.result_items(exercise_index).and_(
            self.page.locator(f"[data-outcome='{outcome}']")
        )

    # --- AI hint locators -------------------------------------------------

    def hint_button(self, exercise_index: int = 0) -> Locator:
        """The Hint button for the exercise at `exercise_index`."""
        return self.exercise_item(exercise_index).get_by_test_id("hint-btn")

    def hint_text(self, exercise_index: int = 0) -> Locator:
        """The hint output paragraph for the exercise at `exercise_index`."""
        return self.exercise_item(exercise_index).get_by_test_id("hint-text")

    def request_hint(self, exercise_index: int = 0) -> "LessonPage":
        """Click Hint for the exercise at `exercise_index` and wait for the text."""
        self.hint_button(exercise_index).click()
        self.hint_text(exercise_index).wait_for(state="visible")
        return self

    # --- AI chat-widget locators ------------------------------------------

    @property
    def chat_toggle(self) -> Locator:
        """The floating chat widget's open toggle."""
        return self.page.get_by_test_id("chat-toggle")

    @property
    def chat_input(self) -> Locator:
        """The chat excerpt textarea."""
        return self.page.get_by_test_id("chat-input")

    @property
    def chat_send(self) -> Locator:
        """The chat send/explain button."""
        return self.page.get_by_test_id("chat-send")

    @property
    def chat_answer(self) -> Locator:
        """The chat answer area."""
        return self.page.get_by_test_id("chat-answer")

    def ask_chat(self, excerpt: str) -> "LessonPage":
        """Open the widget, paste an excerpt, send, and wait for the answer."""
        self.chat_toggle.click()
        self.chat_input.fill(excerpt)
        self.chat_send.click()
        self.chat_answer.wait_for(state="visible")
        return self

    # --- lesson-level locators -------------------------------------------

    @property
    def lesson_title(self) -> Locator:
        """The lesson heading (not an exercise title)."""
        return self.page.get_by_test_id("lesson-title")

    @property
    def progress_counter(self) -> Locator:
        """The lesson-level 'X / N solved' counter."""
        return self.page.get_by_test_id("progress-counter")

    @property
    def lesson_completion(self) -> Locator:
        """The lesson-completed panel (appears when all exercises are solved)."""
        return self.page.get_by_test_id("lesson-completion")

    @property
    def next_lesson_btn(self) -> Locator:
        """The 'Next lesson →' button inside the completion panel."""
        return self.page.get_by_test_id("next-lesson-btn")

    # --- deprecated single-exercise shims (kept for backward compat) ------

    @property
    def exercise_title(self) -> Locator:
        """First exercise title — kept for backward compatibility."""
        return self.first_exercise_title

    @property
    def check_button_first(self) -> Locator:
        """Check button of the first exercise — kept for backward compatibility."""
        return self.check_button(0)

    @property
    def progress_badge(self) -> Locator:
        """Solved badge of the first exercise — kept for backward compatibility."""
        return self.solved_badge(0)
