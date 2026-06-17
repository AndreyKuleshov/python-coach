"""API tests for the AI hint + chat endpoints.

These NEVER reach OpenAI: the in-process app has the LLM dependency overridden
with ``_FakeLLMClient`` (installed in ``conftest.session_maker``), so every call
returns canned text. The 503 (AI-disabled) path is exercised by overriding the
dependency locally with a disabled fake. The locked-lesson 403 is exercised with
a two-lesson curriculum whose second lesson is gated.
"""

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from conftest import FAKE_CHAT_TEXT, FAKE_HINT_TEXT, SeededExercise, _FakeLLMClient
from python_coach.app import app
from python_coach.storage.models.lesson import (
    Exercise,
    ExerciseTranslation,
    Lesson,
    LessonTranslation,
)
from python_coach.transport.deps import get_llm_client

pytestmark = [pytest.mark.db]


# ── hint endpoint ─────────────────────────────────────────────────────────────


@pytest.mark.regression
async def test_hint_requires_token(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """POST /api/exercises/{id}/hint without a bearer token is 401."""
    res = await client.post(
        f"/api/exercises/{seed_exercise.exercise_id}/hint", json={"locale": "en"}
    )
    assert res.status_code == 401


@pytest.mark.smoke
async def test_hint_returns_fake_hint(
    auth_client: httpx.AsyncClient,
    seed_exercise: SeededExercise,
    fake_llm_client: _FakeLLMClient,
) -> None:
    """With a token + the fake LLM, the endpoint returns the canned hint text."""
    fake_llm_client.hint_calls.clear()
    res = await auth_client.post(
        f"/api/exercises/{seed_exercise.exercise_id}/hint", json={"locale": "en"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["hint"] == FAKE_HINT_TEXT
    # The statement was forwarded; the hidden solution_code must NOT have been.
    assert fake_llm_client.hint_calls, "fake hint was not invoked"
    statement, starter, locale = fake_llm_client.hint_calls[-1]
    assert "SECRET_REFERENCE_SOLUTION" not in statement
    assert "SECRET_REFERENCE_SOLUTION" not in starter
    assert locale == "en"


@pytest.mark.regression
async def test_hint_unknown_exercise_is_404(auth_client: httpx.AsyncClient) -> None:
    """A hint for a non-existent exercise is 404."""
    res = await auth_client.post("/api/exercises/999999999/hint", json={"locale": "en"})
    assert res.status_code == 404


@pytest.mark.regression
async def test_hint_disabled_is_503(
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """When the LLM client is disabled (no key), the hint endpoint returns 503."""
    # Save + restore the session-installed fake override rather than popping it,
    # so the global no-real-OpenAI guarantee survives this test.
    previous = app.dependency_overrides[get_llm_client]
    app.dependency_overrides[get_llm_client] = lambda: _FakeLLMClient(enabled=False)
    try:
        res = await auth_client.post(
            f"/api/exercises/{seed_exercise.exercise_id}/hint", json={"locale": "en"}
        )
    finally:
        app.dependency_overrides[get_llm_client] = previous
    assert res.status_code == 503


# ── locked-lesson gating ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LockedExercise:
    """An exercise inside a locked (gated) second lesson."""

    exercise_id: int


@pytest_asyncio.fixture(loop_scope="session")
async def locked_exercise(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[LockedExercise]:
    """Seed a two-lesson curriculum and yield an exercise in the LOCKED 2nd lesson.

    Lesson 2 is locked until lesson 1 is completed (which the shared test account
    has not done), so a hint for its exercise must be refused with 403.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    base = f"qa-ai-lock-{worker}-{uuid.uuid4().hex[:12]}"
    l1_slug, l2_slug = f"{base}-l1", f"{base}-l2"

    locked_id = 0
    async with session_maker() as session:
        # Park existing published lessons so only this pair forms the unlock chain.
        others = (
            await session.exec(select(Lesson).where(Lesson.is_published.is_(True)))  # type: ignore[union-attr]
        ).all()
        parked_ids = [lesson.id or 0 for lesson in others]
        for lesson in others:
            lesson.is_published = False
            session.add(lesson)

        for slug, position in ((l1_slug, 1), (l2_slug, 2)):
            lesson = Lesson(slug=slug, is_published=True, position=position)
            lesson.translations = [
                LessonTranslation(lesson_id=0, locale="en", title=f"L{position}", body_md="# x"),
                LessonTranslation(lesson_id=0, locale="ru", title=f"Л{position}", body_md="# х"),
            ]
            session.add(lesson)
            await session.flush()
            ex = Exercise(lesson_id=lesson.id or 0, slug=f"{slug}-ex", solution_module="solution")
            ex.translations = [
                ExerciseTranslation(exercise_id=0, locale="en", title="ex", statement_md="do x"),
                ExerciseTranslation(exercise_id=0, locale="ru", title="зад", statement_md="х"),
            ]
            session.add(ex)
            await session.flush()
            if position == 2:
                locked_id = ex.id or 0
        await session.commit()

    try:
        yield LockedExercise(exercise_id=locked_id)
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


@pytest.mark.regression
async def test_hint_for_locked_lesson_is_403(
    auth_client: httpx.AsyncClient, locked_exercise: LockedExercise
) -> None:
    """No hints for content the user has not unlocked: a locked exercise is 403."""
    res = await auth_client.post(
        f"/api/exercises/{locked_exercise.exercise_id}/hint", json={"locale": "en"}
    )
    assert res.status_code == 403


# ── chat endpoint ─────────────────────────────────────────────────────────────


@pytest.mark.regression
async def test_chat_requires_token(client: httpx.AsyncClient) -> None:
    """POST /api/chat without a bearer token is 401."""
    res = await client.post("/api/chat", json={"excerpt": "decorators", "locale": "en"})
    assert res.status_code == 401


@pytest.mark.smoke
async def test_chat_returns_fake_answer(
    auth_client: httpx.AsyncClient, fake_llm_client: _FakeLLMClient
) -> None:
    """With a token + the fake LLM, /api/chat returns the canned explanation."""
    fake_llm_client.explain_calls.clear()
    res = await auth_client.post(
        "/api/chat",
        json={"excerpt": "A generator yields values lazily.", "question": "why?", "locale": "ru"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["answer"] == FAKE_CHAT_TEXT
    assert fake_llm_client.explain_calls, "fake explain was not invoked"
    excerpt, question, locale = fake_llm_client.explain_calls[-1]
    assert "generator" in excerpt
    assert question == "why?"
    assert locale == "ru"


@pytest.mark.regression
async def test_chat_disabled_is_503(auth_client: httpx.AsyncClient) -> None:
    """When the LLM client is disabled (no key), /api/chat returns 503."""
    previous = app.dependency_overrides[get_llm_client]
    app.dependency_overrides[get_llm_client] = lambda: _FakeLLMClient(enabled=False)
    try:
        res = await auth_client.post("/api/chat", json={"excerpt": "x", "locale": "en"})
    finally:
        app.dependency_overrides[get_llm_client] = previous
    assert res.status_code == 503


@pytest.mark.regression
async def test_chat_rejects_empty_excerpt(auth_client: httpx.AsyncClient) -> None:
    """An empty excerpt is a 422 (validated min length) — defence against blank calls."""
    res = await auth_client.post("/api/chat", json={"excerpt": "", "locale": "en"})
    assert res.status_code == 422
