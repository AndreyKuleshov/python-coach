"""UI scenarios for lesson completion, sequential unlock, and the profile page.

Drives a real browser against the live uvicorn server. To make the unlock chain
deterministic, the function-scoped `prog_curriculum` fixture parks any other
published lessons for the duration of the test (UI tests run serially) and
restores them on teardown. "Completed" state is seeded directly as solved
Progress rows — no sandbox grading — which is exactly what the unlock logic
reads.

Screenshots for the verification report are written to /tmp.
"""

import asyncio
import os
import uuid
from collections.abc import Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from playwright.sync_api import Page, expect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from fixtures import SeededUser
from python_coach.settings import get_settings
from python_coach.storage.models.lesson import (
    Exercise,
    ExerciseTranslation,
    Lesson,
    LessonTranslation,
)
from python_coach.storage.models.submission import Progress
from python_coach.storage.models.user import User

pytestmark = [pytest.mark.ui]


@dataclass(frozen=True, slots=True)
class ProgCurriculum:
    """Two ordered published lessons (one exercise each) + parked-lesson ids."""

    l1_slug: str
    l2_slug: str
    l1_ex_id: int
    l2_ex_id: int
    parked_ids: list[int]


def _run_isolated[T](coro: Coroutine[object, object, T]) -> T:
    """Run a coroutine on a brand-new loop in a worker thread (see ui/conftest)."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def _lesson(slug: str, position: int) -> Lesson:
    """Build a published lesson with both-locale prose."""
    lesson = Lesson(slug=slug, is_published=True, position=position)
    lesson.translations = [
        LessonTranslation(lesson_id=0, locale="en", title=f"Prog L{position}", body_md="# x"),
        LessonTranslation(lesson_id=0, locale="ru", title=f"Прог Л{position}", body_md="# х"),
    ]
    return lesson


def _exercise(slug: str) -> Exercise:
    """Build one exercise with both-locale prose."""
    ex = Exercise(lesson_id=0, slug=slug, starter_code="", solution_module="solution")
    ex.translations = [
        ExerciseTranslation(exercise_id=0, locale="en", title="ex", statement_md="x"),
        ExerciseTranslation(exercise_id=0, locale="ru", title="зад", statement_md="х"),
    ]
    return ex


async def _seed_curriculum(l1_slug: str, l2_slug: str) -> ProgCurriculum:
    """Park other published lessons and insert the two-lesson sequence."""
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            others = (
                await session.exec(select(Lesson).where(Lesson.is_published.is_(True)))  # type: ignore[union-attr]
            ).all()
            parked = [lesson.id or 0 for lesson in others]
            for lesson in others:
                lesson.is_published = False
                session.add(lesson)
            l1, l2 = _lesson(l1_slug, 1), _lesson(l2_slug, 2)
            session.add_all([l1, l2])
            await session.flush()
            e1, e2 = _exercise(f"{l1_slug}-e0"), _exercise(f"{l2_slug}-e0")
            e1.lesson_id, e2.lesson_id = l1.id or 0, l2.id or 0
            session.add_all([e1, e2])
            await session.commit()
            return ProgCurriculum(
                l1_slug=l1_slug,
                l2_slug=l2_slug,
                l1_ex_id=e1.id or 0,
                l2_ex_id=e2.id or 0,
                parked_ids=parked,
            )
    finally:
        await engine.dispose()


async def _unseed_curriculum(cur: ProgCurriculum) -> None:
    """Delete the seeded pair and republish the parked lessons."""
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            for slug in (cur.l1_slug, cur.l2_slug):
                lesson = (await session.exec(select(Lesson).where(Lesson.slug == slug))).first()
                if lesson is not None:
                    await session.exec(delete(Lesson).where(Lesson.id == lesson.id))  # type: ignore[arg-type, call-overload]
            for lesson_id in cur.parked_ids:
                parked = await session.get(Lesson, lesson_id)
                if parked is not None:
                    parked.is_published = True
                    session.add(parked)
            await session.commit()
    finally:
        await engine.dispose()


async def _solve(email: str, exercise_id: int) -> None:
    """Seed one solved Progress row for `email` against `exercise_id`."""
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            user = (await session.exec(select(User).where(User.email == email))).first()
            assert user is not None
            session.add(
                Progress(
                    user_id=user.id or 0,
                    exercise_id=exercise_id,
                    is_solved=True,
                    attempts=1,
                    solved_at=datetime.now(UTC),
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.fixture
def prog_curriculum() -> Iterator[ProgCurriculum]:
    """Seed the deterministic two-lesson curriculum; restore the DB after."""
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    base = f"qa-progui-{worker}-{uuid.uuid4().hex[:12]}"
    cur = _run_isolated(_seed_curriculum(f"{base}-l1", f"{base}-l2"))
    try:
        yield cur
    finally:
        _run_isolated(_unseed_curriculum(cur))


def _login(page: Page, token: str) -> None:
    """Seed the bearer token so authenticated views are reachable."""
    page.add_init_script(f"window.localStorage.setItem('python-coach.token', '{token}');")


def test_locked_lesson_not_openable_from_list(
    page: Page, live_server: str, seeded_user: SeededUser, prog_curriculum: ProgCurriculum
) -> None:
    """Lesson 1 is unlocked; lesson 2 is locked and clicking it never navigates."""
    _login(page, seeded_user.token)
    page.goto(live_server + "/lessons")
    page.wait_for_selector("[data-testid='lesson-list-item']")

    l1 = page.locator(f"[data-slug='{prog_curriculum.l1_slug}']")
    l2 = page.locator(f"[data-slug='{prog_curriculum.l2_slug}']")
    expect(l1).to_have_attribute("data-state", "current")
    expect(l2).to_have_attribute("data-state", "locked")
    # The locked row has no link and shows a lock indicator.
    expect(l2.locator("a")).to_have_count(0)
    expect(l2.get_by_test_id("lock-indicator")).to_be_visible()

    # Clicking the locked row shows a hint and stays on the list (no navigation).
    l2.get_by_test_id("lesson-locked").click()
    expect(page.get_by_test_id("locked-hint")).to_be_visible()
    expect(page.get_by_test_id("lesson-list")).to_be_visible()

    page.screenshot(path="/tmp/prog_list.png")


def test_completing_lesson_reveals_next_and_unlocks(
    page: Page, live_server: str, seeded_user: SeededUser, prog_curriculum: ProgCurriculum
) -> None:
    """Seeding lesson 1's solve shows ✓ + a Next button and unlocks lesson 2."""
    _run_isolated(_solve(seeded_user.email, prog_curriculum.l1_ex_id))
    _login(page, seeded_user.token)

    # Lesson-1 view shows completed + a Next lesson button.
    page.goto(f"{live_server}/?lesson={prog_curriculum.l1_slug}")
    expect(page.get_by_test_id("lesson-completion")).to_be_visible()
    next_btn = page.get_by_test_id("next-lesson-btn")
    expect(next_btn).to_be_visible()

    # The list shows lesson 1 completed and lesson 2 now unlocked (clickable).
    page.goto(live_server + "/lessons")
    page.wait_for_selector("[data-testid='lesson-list-item']")
    expect(page.locator(f"[data-slug='{prog_curriculum.l1_slug}']")).to_have_attribute(
        "data-state", "completed"
    )
    l2 = page.locator(f"[data-slug='{prog_curriculum.l2_slug}']")
    expect(l2).to_have_attribute("data-state", "current")
    expect(l2.locator("a")).to_have_count(1)

    # Clicking Next from lesson 1 navigates to the now-unlocked lesson 2.
    page.goto(f"{live_server}/?lesson={prog_curriculum.l1_slug}")
    page.get_by_test_id("next-lesson-btn").click()
    expect(page).to_have_url(f"{live_server}/?lesson={prog_curriculum.l2_slug}")
    expect(page.get_by_test_id("lesson-title")).not_to_have_text("")


def test_profile_shows_progress(
    page: Page, live_server: str, seeded_user: SeededUser, prog_curriculum: ProgCurriculum
) -> None:
    """The profile page shows '1 / N completed', a progress bar, and per-lesson rows."""
    _run_isolated(_solve(seeded_user.email, prog_curriculum.l1_ex_id))
    _login(page, seeded_user.token)

    page.goto(live_server + "/profile")
    expect(page.get_by_test_id("profile-section")).to_be_visible()
    expect(page.get_by_test_id("profile-email")).to_have_text(seeded_user.email)
    # Only our two lessons are published, so the summary is "1 / 2 completed".
    expect(page.get_by_test_id("profile-summary")).to_contain_text("1 / 2")
    expect(page.get_by_test_id("profile-progress-bar")).to_be_visible()

    rows = page.get_by_test_id("profile-lesson")
    expect(rows).to_have_count(2)
    expect(
        page.locator(f"[data-testid='profile-lesson'][data-slug='{prog_curriculum.l1_slug}']")
    ).to_have_attribute("data-state", "completed")

    page.screenshot(path="/tmp/prog_profile.png")


def test_locked_lesson_url_redirects(
    page: Page, live_server: str, seeded_user: SeededUser, prog_curriculum: ProgCurriculum
) -> None:
    """Opening a locked lesson URL directly redirects to the list (no content)."""
    _login(page, seeded_user.token)
    page.goto(f"{live_server}/?lesson={prog_curriculum.l2_slug}")
    # The 403 guard bounces to /lessons with a message; content never renders.
    page.wait_for_url(f"{live_server}/lessons")
    expect(page.get_by_test_id("locked-hint")).to_be_visible()
    expect(page.get_by_test_id("lesson-list")).to_be_visible()
