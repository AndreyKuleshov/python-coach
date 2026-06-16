"""API tests for lesson completion, sequential unlock, next-lesson, and profile.

Completion is derived server-side from per-exercise progress; sequential unlock
gates PUBLISHED lessons by position. To set up "completed" state cheaply these
tests seed solved Progress rows directly in the DB (no sandbox grading) — the
unlock chain reads exactly those rows, so it is the right place to test the
gating logic in isolation.

A dedicated two-lesson curriculum is seeded per test (worker-unique slugs) and
torn down via cascade, keeping the suite order-independent under xdist.
"""

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from python_coach.storage.models.lesson import (
    Exercise,
    ExerciseTranslation,
    Lesson,
    LessonTranslation,
)
from python_coach.storage.models.submission import Progress
from python_coach.storage.models.user import User

pytestmark = [pytest.mark.db]


@dataclass(frozen=True, slots=True)
class SeededCurriculum:
    """Two ordered published lessons; lesson 1 has two exercises, lesson 2 one."""

    l1_slug: str
    l2_slug: str
    l1_ex_ids: list[int]
    l2_ex_ids: list[int]


def _exercise(slug: str, position: int) -> Exercise:
    """Build one exercise with both-locale prose (FK filled on flush)."""
    ex = Exercise(
        lesson_id=0, slug=slug, starter_code="", solution_module="solution", position=position
    )
    ex.translations = [
        ExerciseTranslation(exercise_id=0, locale="en", title="ex", statement_md="x"),
        ExerciseTranslation(exercise_id=0, locale="ru", title="зад", statement_md="х"),
    ]
    return ex


def _lesson(slug: str, position: int) -> Lesson:
    """Build one published lesson with both-locale prose."""
    lesson = Lesson(slug=slug, is_published=True, position=position)
    lesson.translations = [
        LessonTranslation(lesson_id=0, locale="en", title=f"L{position}", body_md="# x"),
        LessonTranslation(lesson_id=0, locale="ru", title=f"Л{position}", body_md="# х"),
    ]
    return lesson


@pytest_asyncio.fixture(loop_scope="session")
async def curriculum(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SeededCurriculum]:
    """Seed two ordered published lessons (2 + 1 exercises) as the ONLY curriculum.

    Sequential unlock is a property of the WHOLE published set, so for a
    deterministic unlock test the seeded pair must be the only published
    lessons. Any pre-existing published lessons (real fixtures) are temporarily
    unpublished here and restored on teardown — fully reversible, and the
    session-scoped event loop serialises tests so no other test observes the
    flip. The seeded lessons are cascade-deleted after.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    base = f"qa-prog-{worker}-{uuid.uuid4().hex[:12]}"
    l1_slug, l2_slug = f"{base}-l1", f"{base}-l2"

    async with session_maker() as session:
        # Park other published lessons so only our pair forms the unlock chain.
        others = (
            await session.exec(select(Lesson).where(Lesson.is_published.is_(True)))  # type: ignore[union-attr]
        ).all()
        parked_ids = [lesson.id or 0 for lesson in others]
        for lesson in others:
            lesson.is_published = False
            session.add(lesson)

        l1, l2 = _lesson(l1_slug, 1), _lesson(l2_slug, 2)
        session.add_all([l1, l2])
        await session.flush()
        l1_exs = [_exercise(f"{l1_slug}-e{i}", i) for i in range(2)]
        l2_exs = [_exercise(f"{l2_slug}-e0", 0)]
        for ex in l1_exs:
            ex.lesson_id = l1.id or 0
        for ex in l2_exs:
            ex.lesson_id = l2.id or 0
        session.add_all([*l1_exs, *l2_exs])
        await session.commit()
        seeded = SeededCurriculum(
            l1_slug=l1_slug,
            l2_slug=l2_slug,
            l1_ex_ids=[ex.id or 0 for ex in l1_exs],
            l2_ex_ids=[ex.id or 0 for ex in l2_exs],
        )
    try:
        yield seeded
    finally:
        async with session_maker() as session:
            for slug in (l1_slug, l2_slug):
                lesson = (await session.exec(select(Lesson).where(Lesson.slug == slug))).first()
                if lesson is not None:
                    await session.exec(delete(Lesson).where(Lesson.id == lesson.id))  # type: ignore[arg-type, call-overload]
            # Restore the previously-published lessons.
            for lesson_id in parked_ids:
                parked = await session.get(Lesson, lesson_id)
                if parked is not None:
                    parked.is_published = True
                    session.add(parked)
            await session.commit()


async def _solve(
    session_maker: async_sessionmaker[AsyncSession], email: str, exercise_ids: list[int]
) -> None:
    """Seed solved Progress rows for `email` against the given exercises directly."""
    async with session_maker() as session:
        user = (await session.exec(select(User).where(User.email == email))).first()
        assert user is not None
        for ex_id in exercise_ids:
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


async def _list_item(client: httpx.AsyncClient, slug: str) -> dict[str, object]:
    """Fetch the lessons list and return the row for `slug`."""
    res = await client.get("/api/lessons")
    assert res.status_code == 200
    return next(item for item in res.json() if item["slug"] == slug)


# ── completion derivation ────────────────────────────────────────────────────


async def test_lesson_incomplete_until_all_exercises_solved(
    auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
    curriculum: SeededCurriculum,
) -> None:
    """A lesson is completed only when EVERY exercise is solved (partial != done)."""
    # No solves yet: lesson 1 is not completed.
    row = await _list_item(auth_client, curriculum.l1_slug)
    assert row["is_completed"] is False

    # Solve only the first of two exercises: still not completed.
    await _solve(session_maker, auth_email, curriculum.l1_ex_ids[:1])
    row = await _list_item(auth_client, curriculum.l1_slug)
    assert row["is_completed"] is False, "partial solve must not complete the lesson"

    # Solve the rest: now completed.
    await _solve(session_maker, auth_email, curriculum.l1_ex_ids[1:])
    row = await _list_item(auth_client, curriculum.l1_slug)
    assert row["is_completed"] is True


# ── sequential unlock gating ─────────────────────────────────────────────────


async def test_first_lesson_unlocked_second_locked_initially(
    auth_client: httpx.AsyncClient, curriculum: SeededCurriculum
) -> None:
    """Lesson 1 is unlocked from the start; lesson 2 is locked until 1 is done."""
    l1 = await _list_item(auth_client, curriculum.l1_slug)
    l2 = await _list_item(auth_client, curriculum.l2_slug)
    assert l1["is_unlocked"] is True
    assert l2["is_unlocked"] is False


async def test_second_lesson_unlocks_after_first_completed(
    auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
    curriculum: SeededCurriculum,
) -> None:
    """Completing every exercise in lesson 1 unlocks lesson 2."""
    await _solve(session_maker, auth_email, curriculum.l1_ex_ids)
    l2 = await _list_item(auth_client, curriculum.l2_slug)
    assert l2["is_unlocked"] is True


async def test_get_locked_lesson_is_403(
    auth_client: httpx.AsyncClient, curriculum: SeededCurriculum
) -> None:
    """GET /api/lessons/{slug} returns 403 for a locked lesson (no content served)."""
    res = await auth_client.get(f"/api/lessons/{curriculum.l2_slug}")
    assert res.status_code == 403


async def test_get_unlocked_lesson_is_200(
    auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
    curriculum: SeededCurriculum,
) -> None:
    """Once unlocked, GET /api/lessons/{slug} serves the lesson (200)."""
    await _solve(session_maker, auth_email, curriculum.l1_ex_ids)
    res = await auth_client.get(f"/api/lessons/{curriculum.l2_slug}")
    assert res.status_code == 200
    assert res.json()["slug"] == curriculum.l2_slug


async def test_submission_to_locked_lesson_is_403(
    auth_client: httpx.AsyncClient, curriculum: SeededCurriculum
) -> None:
    """POST /api/submissions to a locked-lesson exercise is rejected with 403."""
    res = await auth_client.post(
        "/api/submissions",
        json={"exercise_id": curriculum.l2_ex_ids[0], "code": "x = 1\n"},
    )
    assert res.status_code == 403


# ── next_slug ────────────────────────────────────────────────────────────────


async def test_next_slug_points_to_following_lesson(
    auth_client: httpx.AsyncClient, curriculum: SeededCurriculum
) -> None:
    """The lesson view exposes next_slug = the next published lesson by position."""
    res = await auth_client.get(f"/api/lessons/{curriculum.l1_slug}")
    assert res.status_code == 200
    assert res.json()["next_slug"] == curriculum.l2_slug


async def test_next_slug_is_null_for_last_lesson(
    auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
    curriculum: SeededCurriculum,
) -> None:
    """The last published lesson reports next_slug = null."""
    # Unlock lesson 2 so we can read it, then assert it has no next.
    await _solve(session_maker, auth_email, curriculum.l1_ex_ids)
    res = await auth_client.get(f"/api/lessons/{curriculum.l2_slug}")
    assert res.status_code == 200
    assert res.json()["next_slug"] is None


async def test_lesson_view_is_completed_flag(
    auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
    curriculum: SeededCurriculum,
) -> None:
    """The lesson view's is_completed reflects all-exercises-solved for the user."""
    before = await auth_client.get(f"/api/lessons/{curriculum.l1_slug}")
    assert before.json()["is_completed"] is False

    await _solve(session_maker, auth_email, curriculum.l1_ex_ids)
    after = await auth_client.get(f"/api/lessons/{curriculum.l1_slug}")
    assert after.json()["is_completed"] is True


# ── profile aggregate ────────────────────────────────────────────────────────


async def test_profile_requires_auth(client: httpx.AsyncClient) -> None:
    """GET /api/profile without a token is 401 (protected endpoint)."""
    res = await client.get("/api/profile")
    assert res.status_code == 401


async def test_profile_aggregate_correctness(
    auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
    curriculum: SeededCurriculum,
) -> None:
    """Profile reports email, per-lesson counts, completion, and totals."""
    await _solve(session_maker, auth_email, curriculum.l1_ex_ids)

    res = await auth_client.get("/api/profile")
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == auth_email

    by_slug = {lesson["slug"]: lesson for lesson in body["lessons"]}
    l1 = by_slug[curriculum.l1_slug]
    l2 = by_slug[curriculum.l2_slug]
    assert l1["total_exercises"] == 2
    assert l1["solved_exercises"] == 2
    assert l1["is_completed"] is True
    assert l1["is_unlocked"] is True
    assert l2["total_exercises"] == 1
    assert l2["solved_exercises"] == 0
    assert l2["is_completed"] is False
    assert l2["is_unlocked"] is True  # unlocked because l1 is completed
    # Totals span all published lessons (>= our two seeded ones).
    assert body["lessons_completed"] >= 1
    assert body["lessons_total"] >= 2


async def test_profile_per_user_isolation(
    auth_client: httpx.AsyncClient,
    second_auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
    curriculum: SeededCurriculum,
) -> None:
    """User A's solves never appear in user B's profile (per-user isolation)."""
    await _solve(session_maker, auth_email, curriculum.l1_ex_ids)

    res = await second_auth_client.get("/api/profile")
    assert res.status_code == 200
    by_slug = {lesson["slug"]: lesson for lesson in res.json()["lessons"]}
    l1 = by_slug[curriculum.l1_slug]
    assert l1["solved_exercises"] == 0, "user B must not see user A's solved exercises"
    assert l1["is_completed"] is False
