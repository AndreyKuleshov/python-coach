"""UI tests for multi-exercise lesson rendering.

Confirms the bug fix: a lesson with N>1 exercises renders ALL N blocks, each
with its own editor and Check button. Verifies:

  1. All exercise blocks render (4 for functions-first-class).
  2. Each block has its own editor, Check button, and solved badge.
  3. Solving one exercise updates only its badge and the progress counter.
  4. The lesson completion panel / Next lesson button appear only when all
     exercises are marked solved (seeded directly, no sandbox grading).
  5. The progress-counter reflects the correct solved count on load when
     progress is pre-seeded.

A screenshot is written to /tmp/multi_ex.png.
"""

import asyncio
from collections.abc import Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from fixtures import SeededUser
from python_coach.settings import get_settings
from python_coach.storage.models.lesson import Exercise, Lesson
from python_coach.storage.models.submission import Progress
from python_coach.storage.models.user import User

pytestmark = [pytest.mark.ui]

# The real published multi-exercise lesson used by most tests.
_MULTI_SLUG = "functions-first-class"
_EXPECTED_EXERCISE_COUNT = 4


def _run_isolated[T](coro: Coroutine[object, object, T]) -> T:
    """Run a coroutine on a brand-new event loop in a worker thread."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def _authed_page(browser: Browser, token: str) -> tuple[BrowserContext, Page]:
    """A fresh context pre-seeded with a bearer token (logged-in path)."""
    ctx = browser.new_context()
    page = ctx.new_page()
    page.add_init_script(f"window.localStorage.setItem('python-coach.token', '{token}');")
    return ctx, page


async def _fetch_exercise_ids(lesson_slug: str) -> list[int]:
    """Return the ordered exercise ids for a lesson from the database."""
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            lesson = (await session.exec(select(Lesson).where(Lesson.slug == lesson_slug))).first()
            if lesson is None:
                return []
            exercises = (
                await session.exec(select(Exercise).where(Exercise.lesson_id == lesson.id))
            ).all()
            return [ex.id or 0 for ex in exercises]
    finally:
        await engine.dispose()


async def _seed_solved(email: str, exercise_ids: list[int]) -> None:
    """Insert solved Progress rows for every exercise in the list."""
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            user = (await session.exec(select(User).where(User.email == email))).first()
            assert user is not None
            for ex_id in exercise_ids:
                existing = (
                    await session.exec(
                        select(Progress).where(
                            Progress.user_id == (user.id or 0),
                            Progress.exercise_id == ex_id,
                        )
                    )
                ).first()
                if existing is None:
                    session.add(
                        Progress(
                            user_id=user.id or 0,
                            exercise_id=ex_id,
                            is_solved=True,
                            attempts=1,
                            solved_at=datetime.now(UTC),
                        )
                    )
            await session.commit()
    finally:
        await engine.dispose()


async def _unseed_progress(email: str, exercise_ids: list[int]) -> None:
    """Remove Progress rows for the user/exercises to avoid cross-test contamination."""
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            user = (await session.exec(select(User).where(User.email == email))).first()
            if user is None:
                return
            for ex_id in exercise_ids:
                # Chain .where() calls to work around pyright's multi-arg type narrowing.
                stmt = delete(Progress).where(Progress.user_id == (user.id or 0))  # type: ignore[arg-type]
                stmt = stmt.where(Progress.exercise_id == ex_id)  # type: ignore[arg-type]
                await session.exec(stmt)  # type: ignore[call-overload]
            await session.commit()
    finally:
        await engine.dispose()


@pytest.fixture
def ex_ids() -> list[int]:
    """Ordered exercise ids for the multi-exercise lesson under test."""
    return _run_isolated(_fetch_exercise_ids(_MULTI_SLUG))


@pytest.fixture
def clean_progress(seeded_user: SeededUser, ex_ids: list[int]) -> Iterator[None]:
    """Ensure no leftover progress rows before the test; clean up after."""
    _run_isolated(_unseed_progress(seeded_user.email, ex_ids))
    yield
    _run_isolated(_unseed_progress(seeded_user.email, ex_ids))


# ── 1. All exercise blocks render ─────────────────────────────────────────────


def test_all_exercises_render(
    browser: Browser, live_server: str, seeded_user: SeededUser, clean_progress: None
) -> None:
    """functions-first-class renders all 4 exercise blocks, each with its own editor."""
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_MULTI_SLUG}")
        # Wait for exercises to render.
        page.locator(".CodeMirror").first.wait_for(state="visible")

        blocks = page.get_by_test_id("exercise-item")
        expect(blocks).to_have_count(_EXPECTED_EXERCISE_COUNT)

        # Every block must have its own editor and Check button.
        editors = page.locator(".CodeMirror")
        expect(editors).to_have_count(_EXPECTED_EXERCISE_COUNT)
        check_btns = page.get_by_test_id("check-btn")
        expect(check_btns).to_have_count(_EXPECTED_EXERCISE_COUNT)

        # Each block carries a data-slug for QA tooling.
        for block in blocks.all():
            slug = block.get_attribute("data-slug")
            assert slug, f"exercise-item missing data-slug: {block.inner_html()[:80]}"

        page.screenshot(path="/tmp/multi_ex.png", full_page=True)
    finally:
        ctx.close()


# ── 2. Progress counter on load ──────────────────────────────────────────────


def test_progress_counter_shows_zero_on_fresh_load(
    browser: Browser, live_server: str, seeded_user: SeededUser, clean_progress: None
) -> None:
    """With no solved exercises the counter reads '0 / 4 solved'."""
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_MULTI_SLUG}")
        page.locator(".CodeMirror").first.wait_for(state="visible")
        # Wait for progress fetches to complete (badges settle).
        page.wait_for_timeout(800)
        counter = page.get_by_test_id("progress-counter")
        expect(counter).to_contain_text("0")
        expect(counter).to_contain_text("4")
    finally:
        ctx.close()


def test_progress_counter_reflects_seeded_progress(
    browser: Browser,
    live_server: str,
    seeded_user: SeededUser,
    ex_ids: list[int],
    clean_progress: None,
) -> None:
    """With 3 pre-solved exercises the counter reads '3 / 4 solved' on load."""
    _run_isolated(_seed_solved(seeded_user.email, ex_ids[:3]))
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_MULTI_SLUG}")
        page.locator(".CodeMirror").first.wait_for(state="visible")
        # Allow progress fetch responses to settle.
        page.wait_for_timeout(800)
        counter = page.get_by_test_id("progress-counter")
        expect(counter).to_contain_text("3")
        expect(counter).to_contain_text("4")
    finally:
        ctx.close()


# ── 3. Solved badges on load ─────────────────────────────────────────────────


def test_solved_badges_shown_for_pre_seeded_exercises(
    browser: Browser,
    live_server: str,
    seeded_user: SeededUser,
    ex_ids: list[int],
    clean_progress: None,
) -> None:
    """Pre-solved exercises show their 'solved' badge without re-submitting."""
    _run_isolated(_seed_solved(seeded_user.email, ex_ids[:2]))
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_MULTI_SLUG}")
        page.locator(".CodeMirror").first.wait_for(state="visible")
        page.wait_for_timeout(800)

        blocks = page.get_by_test_id("exercise-item")
        # First two blocks should show a solved badge.
        for i in range(2):
            badge = blocks.nth(i).get_by_test_id("solved-badge")
            expect(badge).to_contain_text("solved")
        # Third and fourth are not yet solved — badges should be empty.
        for i in range(2, _EXPECTED_EXERCISE_COUNT):
            badge = blocks.nth(i).get_by_test_id("solved-badge")
            expect(badge).to_have_text("")
    finally:
        ctx.close()


# ── 4. Completion panel only appears when all are solved ─────────────────────


def test_completion_panel_hidden_when_not_all_solved(
    browser: Browser,
    live_server: str,
    seeded_user: SeededUser,
    ex_ids: list[int],
    clean_progress: None,
) -> None:
    """Completion panel stays hidden when only some exercises are solved."""
    _run_isolated(_seed_solved(seeded_user.email, ex_ids[:3]))
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_MULTI_SLUG}")
        page.locator(".CodeMirror").first.wait_for(state="visible")
        page.wait_for_timeout(800)

        expect(page.get_by_test_id("lesson-completion")).to_be_hidden()
    finally:
        ctx.close()


def test_completion_panel_visible_when_all_solved(
    browser: Browser,
    live_server: str,
    seeded_user: SeededUser,
    ex_ids: list[int],
    clean_progress: None,
) -> None:
    """Completion panel and Next lesson button appear when all exercises are solved."""
    _run_isolated(_seed_solved(seeded_user.email, ex_ids))
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_MULTI_SLUG}")
        page.locator(".CodeMirror").first.wait_for(state="visible")
        # Progress fetch + lesson re-fetch need to complete.
        page.wait_for_timeout(1200)

        expect(page.get_by_test_id("lesson-completion")).to_be_visible()
        # functions-first-class is not the last lesson — a Next button must appear.
        next_btn = page.get_by_test_id("next-lesson-btn")
        expect(next_btn).to_be_visible()
        expect(next_btn).to_contain_text("Next")
    finally:
        ctx.close()


# ── 5. Independent check — only updates the targeted block ───────────────────


def test_check_updates_only_targeted_block(
    browser: Browser, live_server: str, seeded_user: SeededUser, clean_progress: None
) -> None:
    """After solving exercise 0, only its badge updates; other badges stay empty."""
    all_ids = _run_isolated(_fetch_exercise_ids(_MULTI_SLUG))
    _run_isolated(_unseed_progress(seeded_user.email, all_ids))
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_MULTI_SLUG}")
        page.locator(".CodeMirror").first.wait_for(state="visible")

        blocks = page.get_by_test_id("exercise-item")
        first_block = blocks.nth(0)
        second_block = blocks.nth(1)

        # Verify second block's badge is empty before we do anything.
        expect(second_block.get_by_test_id("solved-badge")).to_have_text("")

        # Submit a correct solution to the first exercise.
        first_editor = page.locator(".CodeMirror").nth(0)
        first_editor.click()
        page.keyboard.press("ControlOrMeta+A")
        page.keyboard.press("Delete")
        solution = "def apply_to_each(func, items):\n    return [func(item) for item in items]\n"
        page.keyboard.type(solution)

        first_block.get_by_test_id("check-btn").click()
        first_block.get_by_test_id("results-panel").wait_for(state="visible")

        # Only the first block's badge should update.
        expect(first_block.get_by_test_id("solved-badge")).to_contain_text("solved")
        # Second block's badge must remain empty.
        expect(second_block.get_by_test_id("solved-badge")).to_have_text("")

        # Progress counter should now show 1 / 4.
        counter = page.get_by_test_id("progress-counter")
        expect(counter).to_contain_text("1")
        expect(counter).to_contain_text("4")
    finally:
        ctx.close()


# ── 6. Screenshot of the multi-exercise lesson ───────────────────────────────


def test_multi_exercise_screenshot(
    browser: Browser, live_server: str, seeded_user: SeededUser, clean_progress: None
) -> None:
    """Capture /tmp/multi_ex.png showing all 4 exercise blocks rendered."""
    ctx, page = _authed_page(browser, seeded_user.token)
    try:
        page.goto(f"{live_server}/?lesson={_MULTI_SLUG}")
        page.locator(".CodeMirror").first.wait_for(state="visible")

        expect(page.get_by_test_id("exercise-item")).to_have_count(_EXPECTED_EXERCISE_COUNT)
        expect(page.get_by_test_id("lesson-title")).not_to_have_text("Loading…")

        page.screenshot(path="/tmp/multi_ex.png", full_page=True)
    finally:
        ctx.close()
