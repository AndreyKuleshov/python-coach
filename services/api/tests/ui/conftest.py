"""Fixtures for the Playwright lesson-page tests.

Unlike the API tests (which drive the app in-process over ASGITransport), the UI
tests need a *real* browser hitting a *real* server, so this conftest:

- boots a uvicorn server on an ephemeral port for the whole session,
- seeds a lesson (passing + failing exercise) reachable by slug, torn down after,
- exposes a `LessonPage` page-object the scenarios act through.

Submissions made from the page run the real Docker sandbox, end to end.
"""

import asyncio
import os
import socket
import subprocess
import time
import uuid
from collections.abc import Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from playwright.sync_api import Browser, BrowserContext, Page
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from fixtures import LocalePageFactory, SeededLesson, SeededUser
from lesson_page import LessonPage
from python_coach.controllers.security import hash_password, mint_access_token
from python_coach.settings import get_settings
from python_coach.storage.models.lesson import (
    Exercise,
    ExerciseTest,
    ExerciseTranslation,
    Lesson,
    LessonTranslation,
)
from python_coach.storage.models.user import User


def _free_port() -> int:
    """Grab an unused TCP port for the throwaway uvicorn server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _seed(slug: str) -> int:
    """Insert a one-exercise lesson (answer() == 42) and return the exercise id."""
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            lesson = Lesson(slug=slug, is_published=True)
            lesson.translations = [
                LessonTranslation(
                    lesson_id=0, locale="en", title="UI seeded lesson", body_md="# ui"
                ),
                LessonTranslation(lesson_id=0, locale="ru", title="UI урок", body_md="# интерфейс"),
            ]
            session.add(lesson)
            await session.flush()
            exercise = Exercise(
                lesson_id=lesson.id or 0,
                slug=f"{slug}-ex",
                starter_code="def answer():\n    return 0\n",
                solution_code="def answer():\n    return 42\n",
                solution_module="solution",
            )
            exercise.translations = [
                ExerciseTranslation(
                    exercise_id=0,
                    locale="en",
                    title="Return 42",
                    statement_md="Implement `answer()` to return 42.",
                ),
                ExerciseTranslation(
                    exercise_id=0,
                    locale="ru",
                    title="Верните 42",
                    statement_md="Реализуйте `answer()`, чтобы вернуть 42.",
                ),
            ]
            session.add(exercise)
            await session.flush()
            test_src = (
                "from solution import answer\n\n\n"
                "def test_answer_returns_42():\n"
                "    assert answer() == 42, 'answer() must return 42'\n"
            )
            session.add(
                ExerciseTest(
                    exercise_id=exercise.id or 0,
                    filename="test_answer.py",
                    content=test_src,
                )
            )
            await session.commit()
            return exercise.id or 0
    finally:
        await engine.dispose()


async def _seed_user(email: str) -> int:
    """Insert a pre-confirmed UI test account and return its id."""
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


async def _unseed_user(email: str) -> None:
    """Delete the UI test account (cascades to its submissions/progress)."""
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


async def _unseed(slug: str) -> None:
    """Delete the seeded lesson (cascades to its exercise/tests/submissions)."""
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            lesson = (await session.exec(select(Lesson).where(Lesson.slug == slug))).first()
            if lesson is not None:
                await session.exec(delete(Lesson).where(Lesson.id == lesson.id))  # type: ignore[arg-type, call-overload]
                await session.commit()
    finally:
        await engine.dispose()


def _run_isolated[T](coro: Coroutine[object, object, T]) -> T:
    """Run a coroutine on a brand-new loop in a worker thread.

    The UI tests are synchronous, but they share a process with pytest-asyncio
    whose session-scoped loop may already be running by the time a session
    fixture seeds the DB. A bare ``asyncio.run`` then raises "cannot be called
    from a running event loop". Running on a dedicated thread's own loop keeps
    the seed independent of whatever loop pytest-asyncio has active.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


@pytest.fixture(scope="session")
def seeded_lesson() -> Iterator[SeededLesson]:
    """Seed a UI lesson once per session and remove it afterwards."""
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    slug = f"qa-ui-{worker}-{uuid.uuid4().hex[:12]}"
    exercise_id = _run_isolated(_seed(slug))
    try:
        yield SeededLesson(slug=slug, exercise_id=exercise_id)
    finally:
        _run_isolated(_unseed(slug))


@pytest.fixture(scope="session")
def seeded_user() -> Iterator[SeededUser]:
    """Seed a confirmed UI account once per session, mint a token, remove it after.

    The token is minted directly with the same secret the app verifies against,
    so the UI flow can be logged in by injecting it into localStorage without
    clicking through the register/confirm forms (those have their own tests).
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    email = f"qa-ui-user-{worker}-{uuid.uuid4().hex[:12]}@example.com"
    user_id = _run_isolated(_seed_user(email))
    settings = get_settings()
    token = mint_access_token(user_id, settings.jwt_secret, settings.jwt_access_token_minutes).token
    try:
        yield SeededUser(email=email, token=token)
    finally:
        _run_isolated(_unseed_user(email))


@pytest.fixture(scope="session")
def live_server() -> Iterator[str]:
    """Run uvicorn on an ephemeral port for the session; yield its base URL.

    SMTP is disabled for the subprocess by blanking the SMTP_HOST (and the auth
    fields) in its environment — this forces ``EmailClient`` onto its log-fallback
    path even when the developer's ``.env`` has real SMTP credentials configured.
    The override is process-level so it covers any future test that registers
    through the live server form without depending on any in-process fake.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    api_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    cmd = [
        "uv",
        "run",
        "uvicorn",
        "python_coach.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    # Inherit the full environment (so DATABASE_URL etc. are present) then blank
    # out every SMTP field so the subprocess never attempts a real send. Likewise
    # force the LLM client into OFFLINE FAKE mode (OPENAI_FAKE=true) so the AI
    # hint + chat UI is exercisable deterministically without spending real
    # tokens — and blank the key so nothing can reach OpenAI even by accident.
    env = {
        **os.environ,
        "SMTP_HOST": "",
        "SMTP_USER": "",
        "SMTP_PASSWORD": "",
        "OPENAI_API_KEY": "",
        "OPENAI_FAKE": "true",
    }
    proc = subprocess.Popen(cmd, cwd=api_dir, env=env)
    try:
        _wait_until_ready(base_url)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _wait_until_ready(base_url: str, timeout_s: float = 30.0) -> None:
    """Poll /healthz until the server answers or the cold-start budget runs out."""
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/healthz", timeout=2).status_code == 200:
                return
        except httpx.HTTPError as err:  # server not up yet
            last_err = err
        time.sleep(0.25)
    raise RuntimeError(f"live server did not become ready at {base_url}: {last_err}")


@pytest.fixture
def lesson_page(
    page: Page, live_server: str, seeded_lesson: SeededLesson, seeded_user: SeededUser
) -> LessonPage:
    """A LessonPage POM pointed at the seeded lesson, pre-authenticated.

    Submitting is gated behind login, so the POM seeds the bearer token into
    localStorage before navigation — the Check button is then enabled.
    """
    return LessonPage(
        page, base_url=live_server, lesson_slug=seeded_lesson.slug, token=seeded_user.token
    )


@pytest.fixture
def locale_page_factory(browser: Browser) -> Iterator[LocalePageFactory]:
    """Yield a factory for locale-pinned pages; close every context on teardown."""
    contexts: list[BrowserContext] = []
    yield LocalePageFactory(browser=browser, _contexts=contexts)
    for context in contexts:
        context.close()
