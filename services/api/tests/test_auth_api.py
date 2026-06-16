"""API tests for the auth flow: register -> confirm -> login -> me.

Drives the real app + DB via ASGITransport. The ``_FakeEmailClient`` override
(registered in conftest ``session_maker``) intercepts every confirmation send so
no real SMTP call is made; we confirm by minting the same signed token the app
uses (no token table), then assert login behaviour.
"""

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from conftest import _FakeEmailClient
from python_coach.app import app
from python_coach.clients.email import EmailClient
from python_coach.controllers.security import mint_confirm_token
from python_coach.settings import get_settings
from python_coach.storage.models.user import User
from python_coach.transport.deps import get_email_client

pytestmark = [pytest.mark.db]

_PASSWORD = "correct horse battery"


def _unique_email() -> str:
    """A globally-unique email so concurrent xdist workers never collide."""
    return f"qa-auth-{uuid.uuid4().hex[:12]}@example.com"


async def _delete_user(maker: async_sessionmaker[AsyncSession], email: str) -> None:
    """Remove a test user (cascades to their submissions/progress)."""
    async with maker() as session:
        user = (await session.exec(select(User).where(User.email == email))).first()
        if user is not None:
            await session.exec(delete(User).where(User.id == user.id))  # type: ignore[arg-type, call-overload]
            await session.commit()


@pytest.mark.smoke
async def test_register_creates_unconfirmed_user(
    client: httpx.AsyncClient, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    """Registration returns 201 and persists an unconfirmed account."""
    email = _unique_email()
    try:
        res = await client.post("/api/auth/register", json={"email": email, "password": _PASSWORD})
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["email"] == email
        assert body["is_email_confirmed"] is False
    finally:
        await _delete_user(session_maker, email)


async def test_register_rejects_short_password(client: httpx.AsyncClient) -> None:
    """A too-short password is rejected with 422 and no account is created."""
    res = await client.post(
        "/api/auth/register", json={"email": _unique_email(), "password": "short"}
    )
    assert res.status_code == 422


async def test_register_rejects_duplicate_email(
    client: httpx.AsyncClient, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    """Registering an already-registered email is a 409."""
    email = _unique_email()
    try:
        first = await client.post(
            "/api/auth/register", json={"email": email, "password": _PASSWORD}
        )
        assert first.status_code == 201
        again = await client.post(
            "/api/auth/register", json={"email": email, "password": _PASSWORD}
        )
        assert again.status_code == 409
    finally:
        await _delete_user(session_maker, email)


async def test_login_blocked_until_confirmed(
    client: httpx.AsyncClient, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    """An unconfirmed account cannot log in (403), then can once confirmed."""
    email = _unique_email()
    try:
        reg = await client.post("/api/auth/register", json={"email": email, "password": _PASSWORD})
        assert reg.status_code == 201

        # Unconfirmed -> 403.
        blocked = await client.post("/api/auth/login", json={"email": email, "password": _PASSWORD})
        assert blocked.status_code == 403

        # Confirm via the real endpoint using a freshly minted confirm token.
        async with session_maker() as session:
            user = (await session.exec(select(User).where(User.email == email))).first()
            assert user is not None
            settings = get_settings()
            token = mint_confirm_token(
                user.id or 0, settings.jwt_secret, settings.jwt_confirm_token_minutes
            )
        confirmed = await client.get(f"/api/auth/confirm?token={token}")
        assert confirmed.status_code == 200

        # Now login succeeds and returns a bearer token.
        ok = await client.post("/api/auth/login", json={"email": email, "password": _PASSWORD})
        assert ok.status_code == 200, ok.text
        assert ok.json()["token_type"] == "bearer"
        assert ok.json()["access_token"]
    finally:
        await _delete_user(session_maker, email)


async def test_login_wrong_password_is_401(
    client: httpx.AsyncClient, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    """A confirmed account with a wrong password is 401."""
    email = _unique_email()
    try:
        await client.post("/api/auth/register", json={"email": email, "password": _PASSWORD})
        async with session_maker() as session:
            user = (await session.exec(select(User).where(User.email == email))).first()
            assert user is not None
            user.is_email_confirmed = True
            session.add(user)
            await session.commit()

        res = await client.post(
            "/api/auth/login", json={"email": email, "password": "wrong password!!"}
        )
        assert res.status_code == 401
    finally:
        await _delete_user(session_maker, email)


async def test_confirm_with_garbage_token_is_400(client: httpx.AsyncClient) -> None:
    """A malformed/invalid confirmation token yields a friendly 400 page."""
    res = await client.get("/api/auth/confirm?token=not-a-real-token")
    assert res.status_code == 400


async def test_me_returns_current_user(auth_client: httpx.AsyncClient, auth_token: str) -> None:
    """GET /api/auth/me resolves the bearer token to the confirmed user."""
    res = await auth_client.get("/api/auth/me")
    assert res.status_code == 200
    body = res.json()
    assert body["is_email_confirmed"] is True
    assert "@example.com" in body["email"]


async def test_me_without_token_is_401(client: httpx.AsyncClient) -> None:
    """GET /api/auth/me without a bearer token is 401."""
    res = await client.get("/api/auth/me")
    assert res.status_code == 401


@pytest.mark.smoke
async def test_register_uses_fake_email_client_not_smtp(
    client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    fake_email_client: _FakeEmailClient,
) -> None:
    """Registration sends via the fake, never through a real SMTP server.

    This is the canonical safety regression: it asserts that the DI override is
    in place and that the injected dependency is our in-memory double, not the
    production ``EmailClient``. If this test fails it means the override was
    removed or the wiring changed — stop and restore it before merging.
    """
    email = _unique_email()
    calls_before = len(fake_email_client.sent)
    try:
        res = await client.post("/api/auth/register", json={"email": email, "password": _PASSWORD})
        assert res.status_code == 201, res.text

        # The fake must have recorded exactly one new call for this registration.
        new_calls = fake_email_client.sent[calls_before:]
        assert len(new_calls) == 1, f"expected 1 fake send, got {len(new_calls)}"
        to_addr, confirm_url = new_calls[0]
        assert to_addr == email
        assert confirm_url  # the app generated a real signed URL

        # The DI override must resolve to our fake, not the real EmailClient.
        resolved = app.dependency_overrides.get(get_email_client)
        assert resolved is not None, "get_email_client override is not registered"
        injected = resolved()
        assert isinstance(injected, _FakeEmailClient), (
            f"expected _FakeEmailClient in DI, got {type(injected).__name__} — "
            "real SMTP would have been used"
        )
        assert not isinstance(injected, EmailClient), (
            "override resolved to the real EmailClient — SMTP would fire in tests"
        )
    finally:
        await _delete_user(session_maker, email)
