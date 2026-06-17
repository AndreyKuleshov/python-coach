"""Shared fixtures for the API test suite.

These drive the *real* stack: the in-process FastAPI app over ASGITransport, a
real Postgres (per ``database_url`` in the API ``.env``), and — for the flow /
security tests — the real Docker sandbox. The only sanctioned fake is the
reversible DB seed/teardown below: each test owns a uniquely-slugged lesson so
the suite is order-independent and safe under ``pytest-xdist``.

Why a dedicated test engine: the app's production engine (``storage.db``) is a
process-global lazily bound to the first event loop it sees. Sharing it across
pytest-asyncio's per-test loops closes its pooled asyncpg connections mid-run
("Event loop is closed"). We instead build one session-scoped engine on the
session loop and point the app's ``get_session`` dependency at it — no product
code changes, just dependency-injection wiring that FastAPI exposes for exactly
this purpose.

SMTP guarantee: ``_FakeEmailClient`` is registered via ``app.dependency_overrides``
in ``session_maker`` so every in-process call to ``/api/auth/register`` hits the
fake, never a real SMTP server — regardless of what ``.env`` contains.
"""

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from python_coach.app import app
from python_coach.settings import get_settings
from python_coach.storage.db import get_session
from python_coach.storage.models.lesson import (
    Exercise,
    ExerciseTest,
    ExerciseTranslation,
    Lesson,
    LessonTranslation,
)
from python_coach.storage.models.user import User
from python_coach.transport.deps import get_email_client, get_llm_client


@dataclass
class _FakeEmailClient:
    """In-memory email double — records calls, never touches SMTP.

    Registered via ``app.dependency_overrides`` so every in-process register
    route call lands here instead of the real ``EmailClient``. Tests can inspect
    ``sent`` to assert that confirmation links were generated without relying on
    log scraping or SMTP side-effects.
    """

    sent: list[tuple[str, str]] = field(default_factory=list)

    async def send_confirmation(self, to_email: str, confirm_url: str) -> None:
        """Record the outbound confirmation without touching any SMTP server."""
        self.sent.append((to_email, confirm_url))


# Session-scoped fake so every test in the suite shares the same instance and
# the override stays registered for the full run.
_fake_email_client = _FakeEmailClient()


# Canned text the LLM fake returns — distinct per method so tests can assert
# which path was exercised without ever reaching the real OpenAI API.
FAKE_HINT_TEXT = "FAKE_HINT: think about the return value."
FAKE_CHAT_TEXT = "FAKE_CHAT: this excerpt explains the core idea."


@dataclass
class _FakeLLMClient:
    """In-memory LLM double — returns canned text, NEVER calls OpenAI.

    Mirrors ``_FakeEmailClient``: registered via ``app.dependency_overrides`` so
    every in-process hint/chat call lands here. ``enabled`` defaults True so the
    feature is on; tests that need the disabled (503) path build an instance with
    ``enabled=False`` and override the dependency locally.
    """

    enabled: bool = True
    hint_calls: list[tuple[str, str, str]] = field(default_factory=list)
    explain_calls: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def is_enabled(self) -> bool:
        """Whether the AI features are offered (matches LLMClient.is_enabled)."""
        return self.enabled

    async def hint(self, statement: str, starter_code: str, locale: str) -> str:
        """Record the call and return canned hint text — no network."""
        self.hint_calls.append((statement, starter_code, locale))
        return FAKE_HINT_TEXT

    async def explain(self, excerpt: str, question: str, locale: str) -> str:
        """Record the call and return canned explanation text — no network."""
        self.explain_calls.append((excerpt, question, locale))
        return FAKE_CHAT_TEXT


# Session-scoped enabled fake, installed globally like the email fake.
_fake_llm_client = _FakeLLMClient()


@pytest.fixture(scope="session", autouse=True)
def _install_external_client_fakes() -> Iterator[None]:
    """Force the email + LLM dependencies onto their fakes for the WHOLE session.

    Autouse + session-scoped so it is active for every in-process test, even ones
    that only use the bare ``client`` fixture (which does not pull in
    ``session_maker``). This is the hard guarantee that NO test reaches a real
    SMTP server or the real OpenAI API regardless of what ``.env`` contains.
    """
    app.dependency_overrides[get_email_client] = lambda: _fake_email_client
    app.dependency_overrides[get_llm_client] = lambda: _fake_llm_client
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_email_client, None)
        app.dependency_overrides.pop(get_llm_client, None)


# Sentinel reference solution seeded on every exercise so the leak tests can
# assert it never reaches the lesson API.
SEEDED_SOLUTION_CODE = "def answer():\n    return 42  # SECRET_REFERENCE_SOLUTION\n"


@dataclass(frozen=True, slots=True)
class SeededExercise:
    """Ids of a freshly-seeded exercise plus the visible/hidden test it carries."""

    lesson_id: int
    lesson_slug: str
    exercise_id: int
    exercise_slug: str
    visible_test_filename: str
    hidden_test_filename: str
    solution_code: str


@dataclass(frozen=True, slots=True)
class TestSpec:
    """One pytest file to attach to a seeded exercise."""

    filename: str
    content: str
    is_hidden: bool = False


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def session_maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A test-owned engine on the session loop, wired into the app's get_session.

    Building the engine here (rather than reusing the global one) keeps every
    pooled connection bound to the single session-scoped event loop the whole
    suite runs on, which is what makes the async DB tests stable.
    """
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    # The email + LLM fakes are installed by the session-scoped autouse fixture
    # `_install_external_client_fakes`; here we only point get_session at the
    # test engine. (Keeping the external-client fakes in a separate autouse
    # fixture means even bare-`client` tests, which never pull in session_maker,
    # are still protected from real SMTP / OpenAI calls.)
    app.dependency_overrides[get_session] = _override_get_session
    try:
        yield maker
    finally:
        app.dependency_overrides.pop(get_session, None)
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """An in-process HTTP client bound to the real FastAPI app (no live port)."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@dataclass(frozen=True, slots=True)
class AuthAccount:
    """A confirmed test account: its email plus a live bearer token."""

    email: str
    token: str


@pytest_asyncio.fixture(loop_scope="session")
async def auth_account(
    client: httpx.AsyncClient, session_maker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AuthAccount]:
    """Register a unique user, confirm them directly in the DB, and log in.

    The email override (``_FakeEmailClient``) absorbs the confirmation send so
    no real SMTP call is made. We flip ``is_email_confirmed`` straight in the DB
    (the migration's own fast path) rather than following the link, then log in
    through the real endpoint to obtain a JWT. The user is deleted afterwards so
    the suite stays order-independent under xdist. Exposes the email too so
    progression tests can seed solved Progress for it.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    email = f"qa-{worker}-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct horse battery"  # >= 8 chars

    reg = await client.post("/api/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 201, reg.text

    # Confirm directly in the DB (equivalent to following the logged link).
    async with session_maker() as session:
        user = (await session.exec(select(User).where(User.email == email))).first()
        assert user is not None
        user.is_email_confirmed = True
        session.add(user)
        await session.commit()

    login = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    try:
        yield AuthAccount(email=email, token=token)
    finally:
        async with session_maker() as session:
            user = (await session.exec(select(User).where(User.email == email))).first()
            if user is not None:
                await session.exec(delete(User).where(User.id == user.id))  # type: ignore[arg-type, call-overload]
                await session.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def auth_token(auth_account: AuthAccount) -> str:
    """The bearer token for the shared confirmed test account."""
    return auth_account.token


@pytest_asyncio.fixture(loop_scope="session")
async def auth_email(auth_account: AuthAccount) -> str:
    """The email of the shared confirmed test account (for seeding its progress)."""
    return auth_account.email


@pytest_asyncio.fixture(loop_scope="session")
async def auth_client(auth_token: str) -> AsyncIterator[httpx.AsyncClient]:
    """An in-process client that sends `Authorization: Bearer <token>` on every request."""
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {auth_token}"}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers=headers
    ) as ac:
        yield ac


@pytest_asyncio.fixture(loop_scope="session")
async def second_auth_client(
    client: httpx.AsyncClient, session_maker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[httpx.AsyncClient]:
    """A second, independent authenticated user — used for cross-user IDOR tests.

    Deliberately separate from `auth_token`/`auth_client` so the two users are
    distinct DB rows. Worker-unique email keeps this xdist-safe.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    email = f"qa-b-{worker}-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct horse battery"

    reg = await client.post("/api/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 201, reg.text

    async with session_maker() as session:
        user = (await session.exec(select(User).where(User.email == email))).first()
        assert user is not None
        user.is_email_confirmed = True
        session.add(user)
        await session.commit()

    login = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as ac:
            yield ac
    finally:
        async with session_maker() as session:
            user = (await session.exec(select(User).where(User.email == email))).first()
            if user is not None:
                await session.exec(delete(User).where(User.id == user.id))  # type: ignore[arg-type, call-overload]
                await session.commit()


@pytest.fixture(scope="session")
def fake_email_client() -> _FakeEmailClient:
    """Expose the session-scoped email fake so tests can assert on captured calls."""
    return _fake_email_client


@pytest.fixture(scope="session")
def fake_llm_client() -> _FakeLLMClient:
    """Expose the session-scoped LLM fake so tests can assert on captured calls."""
    return _fake_llm_client


@pytest.fixture
def unique_slug() -> str:
    """A globally-unique slug so concurrent xdist workers never collide on data."""
    # Worker id keeps slugs distinct across processes; uuid keeps them distinct in-process.
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    return f"qa-{worker}-{uuid.uuid4().hex[:12]}"


@pytest_asyncio.fixture(loop_scope="session")
async def seed_exercise(
    unique_slug: str, session_maker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[SeededExercise]:
    """Seed a lesson + one exercise with a visible and a hidden test; delete it after.

    The default exercise checks ``answer() == 42`` — a tiny, deterministic task
    used by the lesson/submission/progress flow tests. Deleting the lesson
    cascades to its exercises, tests, submissions and progress rows, so teardown
    leaves the DB exactly as it was found.
    """
    visible = TestSpec(
        filename="test_answer.py",
        content=(
            "from solution import answer\n\n\n"
            "def test_answer_returns_42():\n"
            "    assert answer() == 42, 'answer() must return 42'\n"
        ),
    )
    hidden = TestSpec(
        filename="test_answer_hidden.py",
        content=(
            "from solution import answer\n\n\n"
            "def test_answer_is_int():\n"
            "    assert isinstance(answer(), int)\n"
        ),
        is_hidden=True,
    )
    async with seed_lesson(session_maker, unique_slug, [visible, hidden]) as seeded:
        yield seeded


@dataclass(frozen=True, slots=True)
class SeededPair:
    """Two published lessons with deliberately out-of-order positions.

    `low` has the smaller `position` and so must come first in the list payload
    even though it is inserted second — that is exactly the ordering assertion.
    """

    low_slug: str
    high_slug: str


@pytest_asyncio.fixture(loop_scope="session")
async def seed_ordered_pair(
    unique_slug: str, session_maker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[SeededPair]:
    """Seed two published lessons whose positions are inverted vs insert order.

    Inserting the high-position lesson first and asserting the low-position one
    leads the list proves the API orders by `position`, not by id/insert order.
    """
    high_slug = f"{unique_slug}-pos9"
    low_slug = f"{unique_slug}-pos1"
    async with session_maker() as session:
        # Insert high first so a naive id/insert ordering would put it on top.
        for slug, position in ((high_slug, 9), (low_slug, 1)):
            lesson = Lesson(slug=slug, is_published=True, position=position)
            lesson.translations = [
                LessonTranslation(lesson_id=0, locale="en", title=f"L{position}", body_md="# x"),
                LessonTranslation(lesson_id=0, locale="ru", title=f"Л{position}", body_md="# х"),
            ]
            session.add(lesson)
        await session.commit()
    try:
        yield SeededPair(low_slug=low_slug, high_slug=high_slug)
    finally:
        async with session_maker() as session:
            for slug in (high_slug, low_slug):
                lesson = (await session.exec(select(Lesson).where(Lesson.slug == slug))).first()
                if lesson is not None:
                    await session.exec(delete(Lesson).where(Lesson.id == lesson.id))  # type: ignore[arg-type, call-overload]
            await session.commit()


def _build_rows(slug: str, tests: list[TestSpec]) -> tuple[Lesson, Exercise, list[ExerciseTest]]:
    """Build the ORM objects for a one-exercise lesson (not yet persisted).

    Translations are attached via the relationship (FK filled by SQLAlchemy on
    flush), so we do not pass lesson_id/exercise_id to the translation rows.
    """
    lesson = Lesson(slug=slug, is_published=True)
    lesson.translations = [
        LessonTranslation(lesson_id=0, locale="en", title="QA seeded lesson", body_md="# seeded"),
        LessonTranslation(lesson_id=0, locale="ru", title="QA урок", body_md="# посев"),
    ]
    exercise = Exercise(
        lesson_id=0,
        slug=f"{slug}-ex",
        starter_code="def answer():\n    return 0\n",
        solution_code=SEEDED_SOLUTION_CODE,
        solution_module="solution",
        position=0,
    )
    exercise.translations = [
        ExerciseTranslation(
            exercise_id=0,
            locale="en",
            title="QA exercise",
            statement_md="Return 42 from `answer()`.",
        ),
        ExerciseTranslation(
            exercise_id=0, locale="ru", title="QA задача", statement_md="Верните 42 из `answer()`."
        ),
    ]
    rows = [
        ExerciseTest(
            exercise_id=0,
            filename=t.filename,
            content=t.content,
            is_hidden=t.is_hidden,
            position=i,
        )
        for i, t in enumerate(tests)
    ]
    return lesson, exercise, rows


class _SeedContext:
    """Async context manager that persists a seeded lesson and removes it on exit."""

    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        slug: str,
        tests: list[TestSpec],
    ) -> None:
        self._maker = maker
        self._slug = slug
        self._tests = tests

    async def __aenter__(self) -> SeededExercise:
        lesson, exercise, rows = _build_rows(self._slug, self._tests)
        async with self._maker() as session:
            session.add(lesson)
            await session.flush()
            exercise.lesson_id = lesson.id or 0
            session.add(exercise)
            await session.flush()
            for row in rows:
                row.exercise_id = exercise.id or 0
                session.add(row)
            await session.commit()
            visible = next(t for t in self._tests if not t.is_hidden)
            hidden = next(t for t in self._tests if t.is_hidden)
            return SeededExercise(
                lesson_id=lesson.id or 0,
                lesson_slug=lesson.slug,
                exercise_id=exercise.id or 0,
                exercise_slug=exercise.slug,
                visible_test_filename=visible.filename,
                hidden_test_filename=hidden.filename,
                solution_code=SEEDED_SOLUTION_CODE,
            )

    async def __aexit__(self, *_exc: object) -> None:
        # Deleting the lesson cascades to exercises/tests/submissions/progress.
        async with self._maker() as session:
            lesson = (await session.exec(select(Lesson).where(Lesson.slug == self._slug))).first()
            if lesson is not None:
                await session.exec(delete(Lesson).where(Lesson.id == lesson.id))  # type: ignore[arg-type, call-overload]
                await session.commit()


def seed_lesson(
    maker: async_sessionmaker[AsyncSession], slug: str, tests: list[TestSpec]
) -> _SeedContext:
    """Return a context manager that seeds `tests` under a one-exercise lesson `slug`."""
    return _SeedContext(maker, slug, tests)
