"""API tests for GET /api/exercises/{exercise_id}/solution.

Authorization contract:
  - 401 with no token.
  - 403 when the exercise belongs to a locked lesson.
  - 403 when the user has not solved the exercise.
  - 404 for an unknown exercise id.
  - 404 when solution_code is blank/missing.
  - 200 + solution_code when the user has a solved Progress row.

Per-user isolation: user A solved → A gets it; user B (not solved) → 403.

The lesson detail/list endpoints must STILL not expose solution_code — that
assertion lives in test_lessons_api.py and is not duplicated here, but the
raw-bytes check below confirms it for the solution endpoint boundary.
"""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from conftest import SEEDED_SOLUTION_CODE, SeededExercise, TestSpec, seed_lesson
from python_coach.storage.models.lesson import (
    Exercise,
    ExerciseTranslation,
    Lesson,
    LessonTranslation,
)
from python_coach.storage.models.submission import Progress
from python_coach.storage.models.user import User

pytestmark = [pytest.mark.db]


# ── helpers ───────────────────────────────────────────────────────────────────


async def _seed_solved_progress(
    session_maker: async_sessionmaker[AsyncSession],
    email: str,
    exercise_id: int,
) -> None:
    """Insert a solved Progress row for the given user+exercise directly in the DB."""
    async with session_maker() as session:
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


# ── 401 without a token ───────────────────────────────────────────────────────


async def test_solution_requires_auth(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """GET /api/exercises/{id}/solution without a token yields 401."""
    res = await client.get(f"/api/exercises/{seed_exercise.exercise_id}/solution")
    assert res.status_code == 401


# ── 404 unknown exercise ──────────────────────────────────────────────────────


async def test_solution_unknown_exercise_is_404(auth_client: httpx.AsyncClient) -> None:
    """A non-existent exercise id yields 404, not 403 or 500."""
    res = await auth_client.get("/api/exercises/99999999/solution")
    assert res.status_code == 404


# ── 403 not solved ────────────────────────────────────────────────────────────


async def test_solution_not_solved_is_403(
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """A user who has not solved the exercise gets 403, not the solution."""
    res = await auth_client.get(f"/api/exercises/{seed_exercise.exercise_id}/solution")
    assert res.status_code == 403
    # The seeded sentinel must not leak in the error body.
    assert "SECRET_REFERENCE_SOLUTION" not in res.text


# ── 200 when solved ───────────────────────────────────────────────────────────


async def test_solution_200_after_solving(
    auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
    seed_exercise: SeededExercise,
) -> None:
    """After seeding a solved Progress row the endpoint returns 200 + solution_code."""
    await _seed_solved_progress(session_maker, auth_email, seed_exercise.exercise_id)

    res = await auth_client.get(f"/api/exercises/{seed_exercise.exercise_id}/solution")
    assert res.status_code == 200
    body = res.json()
    assert "solution_code" in body
    assert body["solution_code"] == SEEDED_SOLUTION_CODE


# ── per-user isolation ────────────────────────────────────────────────────────


async def test_solution_isolation_other_user_403(
    auth_client: httpx.AsyncClient,
    second_auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
    seed_exercise: SeededExercise,
) -> None:
    """User A solved → A gets 200; user B (not solved) → 403.

    Confirms per-user gating: a solve in one account must not unlock the
    solution endpoint for another user's session.
    """
    # Seed user A as solved.
    await _seed_solved_progress(session_maker, auth_email, seed_exercise.exercise_id)

    a_res = await auth_client.get(f"/api/exercises/{seed_exercise.exercise_id}/solution")
    assert a_res.status_code == 200

    b_res = await second_auth_client.get(f"/api/exercises/{seed_exercise.exercise_id}/solution")
    assert b_res.status_code == 403
    assert "SECRET_REFERENCE_SOLUTION" not in b_res.text


# ── 403 locked lesson ─────────────────────────────────────────────────────────


async def test_solution_locked_lesson_is_403(
    auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """An exercise in a locked lesson yields 403 even if solution_code is stored.

    We seed a two-lesson curriculum (L1 → L2) with only one published lesson, so
    L2 is locked. The test checks that the solution endpoint honours the same
    sequential-unlock gate used by the submission endpoint.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    base = f"qa-sol-lock-{worker}-{uuid.uuid4().hex[:8]}"
    l1_slug = f"{base}-l1"
    l2_slug = f"{base}-l2"

    async with session_maker() as session:
        # Park existing published lessons so only our pair is in the unlock chain.
        others = (
            await session.exec(select(Lesson).where(Lesson.is_published.is_(True)))  # type: ignore[union-attr]
        ).all()
        parked_ids = [lesson.id or 0 for lesson in others]
        for lesson in others:
            lesson.is_published = False
            session.add(lesson)

        # L1 (position 1) — user will NOT solve it, keeping L2 locked.
        l1 = Lesson(slug=l1_slug, is_published=True, position=1)
        l1.translations = [
            LessonTranslation(lesson_id=0, locale="en", title="L1", body_md="# l1"),
            LessonTranslation(lesson_id=0, locale="ru", title="Л1", body_md="# л1"),
        ]
        l2 = Lesson(slug=l2_slug, is_published=True, position=2)
        l2.translations = [
            LessonTranslation(lesson_id=0, locale="en", title="L2", body_md="# l2"),
            LessonTranslation(lesson_id=0, locale="ru", title="Л2", body_md="# л2"),
        ]
        session.add_all([l1, l2])
        await session.flush()

        l1_ex = Exercise(
            lesson_id=l1.id or 0,
            slug=f"{l1_slug}-ex",
            starter_code="",
            solution_code="print('l1')",
            solution_module="solution",
        )
        l1_ex.translations = [
            ExerciseTranslation(exercise_id=0, locale="en", title="ex", statement_md="x"),
            ExerciseTranslation(exercise_id=0, locale="ru", title="зад", statement_md="х"),
        ]
        l2_ex = Exercise(
            lesson_id=l2.id or 0,
            slug=f"{l2_slug}-ex",
            starter_code="",
            solution_code=SEEDED_SOLUTION_CODE,
            solution_module="solution",
        )
        l2_ex.translations = [
            ExerciseTranslation(exercise_id=0, locale="en", title="ex2", statement_md="y"),
            ExerciseTranslation(exercise_id=0, locale="ru", title="зад2", statement_md="у"),
        ]
        session.add_all([l1_ex, l2_ex])
        await session.commit()
        l2_ex_id = l2_ex.id or 0

    try:
        # L2 is locked (L1 not solved); even with a hypothetical solved row it is gated.
        res = await auth_client.get(f"/api/exercises/{l2_ex_id}/solution")
        assert res.status_code == 403
        assert "SECRET_REFERENCE_SOLUTION" not in res.text
    finally:
        async with session_maker() as session:
            for slug in (l1_slug, l2_slug):
                lesson = (await session.exec(select(Lesson).where(Lesson.slug == slug))).first()
                if lesson is not None:
                    await session.exec(delete(Lesson).where(Lesson.id == lesson.id))  # type: ignore[arg-type, call-overload]
            for lesson_id in parked_ids:
                parked = await session.get(Lesson, lesson_id)
                if parked is not None:
                    parked.is_published = True
                    session.add(parked)
            await session.commit()


# ── 404 blank solution_code ───────────────────────────────────────────────────


@pytest_asyncio.fixture(loop_scope="session")
async def seed_no_solution(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[int]:
    """Seed an exercise whose solution_code is None (not set by the methodist).

    Returns the exercise id. Torn down via lesson cascade after the test.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    slug = f"qa-nosol-{worker}-{uuid.uuid4().hex[:10]}"
    visible = TestSpec(
        filename="test_x.py",
        content="def test_x():\n    pass\n",
    )
    hidden = TestSpec(
        filename="test_x_hidden.py",
        content="def test_y():\n    pass\n",
        is_hidden=True,
    )
    async with seed_lesson(session_maker, slug, [visible, hidden]) as seeded:
        # Blank out the solution_code that the fixture seeds by default.
        async with session_maker() as session:
            ex = await session.get(Exercise, seeded.exercise_id)
            if ex is not None:
                ex.solution_code = None
                session.add(ex)
                await session.commit()
        yield seeded.exercise_id


async def test_solution_blank_is_404(
    auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
    seed_no_solution: int,
) -> None:
    """If solution_code is blank/None, the endpoint returns 404 instead of an empty leak."""
    await _seed_solved_progress(session_maker, auth_email, seed_no_solution)
    res = await auth_client.get(f"/api/exercises/{seed_no_solution}/solution")
    assert res.status_code == 404


# ── lesson list/detail still never expose solution_code ───────────────────────


async def test_lesson_detail_still_no_solution_code(
    auth_client: httpx.AsyncClient,
    auth_email: str,
    session_maker: async_sessionmaker[AsyncSession],
    seed_exercise: SeededExercise,
) -> None:
    """After solving, GET /api/lessons/{slug} still never leaks solution_code.

    Guards against accidental leakage via the lesson endpoint now that a
    solution endpoint exists in the codebase.
    """
    await _seed_solved_progress(session_maker, auth_email, seed_exercise.exercise_id)

    res = await auth_client.get(f"/api/lessons/{seed_exercise.lesson_slug}")
    assert res.status_code == 200
    assert "solution_code" not in res.json()["exercises"][0]
    assert "SECRET_REFERENCE_SOLUTION" not in res.text
