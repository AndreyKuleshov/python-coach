"""UI tests for the reference-solution reveal feature.

Verifies:
  1. "Show reference solution" button is absent when the exercise is NOT solved.
  2. After solving (via real sandbox submission), the button appears.
  3. Clicking it reveals a read-only textarea with the solution text.
  4. A second click hides the textarea (toggle).

Uses the session-scoped seeded_lesson / seeded_user / live_server fixtures from
conftest.py. The seeded exercise has solution_code = "def answer():\n    return 42\n"
(set in conftest.py _seed()). Clicking Check with the correct answer triggers the
real Docker sandbox — same pattern as test_lesson_flow.py.

test_show_solution_btn_absent_before_solving gets its own function-scoped user
(zero progress) so sibling tests that submit cannot bleed solved state into it,
regardless of execution order.
"""

import asyncio
import os
import uuid
from collections.abc import Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from playwright.sync_api import Page, expect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from fixtures import SeededLesson
from lesson_page import LessonPage
from python_coach.controllers.security import hash_password, mint_access_token
from python_coach.settings import get_settings
from python_coach.storage.models.user import User

pytestmark = [pytest.mark.ui]

_CORRECT = "def answer():\n    return 42\n"


def _run_isolated[T](coro: Coroutine[object, object, T]) -> T:
    """Run a coroutine on a dedicated loop in a worker thread (avoids pytest-asyncio's loop)."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


async def _seed_fresh_user(email: str) -> int:
    """Insert a confirmed account with zero progress and return its id."""
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            user = User(
                email=email,
                password_hash=hash_password("ui-password-123"),
                is_email_confirmed=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user.id or 0
    finally:
        await engine.dispose()


async def _remove_fresh_user(email: str) -> None:
    """Delete the transient test account (cascades to any submissions/progress)."""
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            user = (await session.exec(select(User).where(User.email == email))).first()
            if user is not None:
                await session.exec(delete(User).where(User.id == user.id))  # type: ignore[arg-type, call-overload]
                await session.commit()
    finally:
        await engine.dispose()


@pytest.fixture
def fresh_unsolved_lesson_page(
    page: Page, live_server: str, seeded_lesson: SeededLesson
) -> Iterator[LessonPage]:
    """A LessonPage for a brand-new user who has zero progress on any exercise.

    Function-scoped so each call gets a virgin account — no sibling test that
    submits can poison this user's progress regardless of test-execution order.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    email = f"qa-ui-fresh-{worker}-{uuid.uuid4().hex[:12]}@example.com"
    user_id = _run_isolated(_seed_fresh_user(email))
    settings = get_settings()
    token = mint_access_token(
        user_id, settings.jwt_secret, settings.jwt_access_token_minutes
    ).token
    lp = LessonPage(page, base_url=live_server, lesson_slug=seeded_lesson.slug, token=token)
    try:
        yield lp
    finally:
        _run_isolated(_remove_fresh_user(email))


def test_show_solution_btn_absent_before_solving(
    fresh_unsolved_lesson_page: LessonPage,
) -> None:
    """The reference-solution button must not exist until the exercise is solved.

    Uses a fresh user with zero progress so execution order of sibling tests
    cannot pre-solve the exercise and make the button visible prematurely.
    """
    fresh_unsolved_lesson_page.open()

    # The button is rendered in the DOM but hidden; expect it to be hidden.
    btn = fresh_unsolved_lesson_page.show_solution_btn()
    expect(btn).to_be_hidden()


def test_show_solution_btn_appears_after_solving(lesson_page: LessonPage) -> None:
    """After a passing submission the 'Show reference solution' button becomes visible."""
    lesson_page.open().set_solution(_CORRECT).submit()

    # The check submission must pass first.
    expect(lesson_page.solved_badge()).to_contain_text("solved")

    btn = lesson_page.show_solution_btn()
    expect(btn).to_be_visible()


def test_clicking_show_solution_reveals_textarea(lesson_page: LessonPage) -> None:
    """Clicking the button fetches and reveals the read-only reference-solution textarea."""
    lesson_page.open().set_solution(_CORRECT).submit()
    expect(lesson_page.solved_badge()).to_contain_text("solved")

    lesson_page.show_solution_btn().click()

    ta = lesson_page.reference_solution()
    expect(ta).to_be_visible()
    # The seeded solution is "def answer():\n    return 42\n".
    expect(ta).to_have_value("def answer():\n    return 42\n")


def test_clicking_show_solution_again_hides_textarea(lesson_page: LessonPage) -> None:
    """A second click on the button hides the textarea (toggle behaviour)."""
    lesson_page.open().set_solution(_CORRECT).submit()
    expect(lesson_page.solved_badge()).to_contain_text("solved")

    btn = lesson_page.show_solution_btn()
    btn.click()
    expect(lesson_page.reference_solution()).to_be_visible()

    btn.click()
    expect(lesson_page.reference_solution()).to_be_hidden()
