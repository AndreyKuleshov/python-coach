"""Auth endpoints: register, confirm email, login, current user.

Transport layer: maps the auth use-case outcomes/exceptions to HTTP and shapes
the response DTOs. These auth routes are the ONLY public endpoints; all
content (lessons, submissions, progress) is protected via the CurrentUserDep
dependency (wired in those routers).
"""

import html
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from python_coach.controllers.auth import (
    ConfirmationFailedError,
    EmailAlreadyRegisteredError,
    EmailNotConfirmedError,
    InvalidCredentialsError,
    WeakPasswordError,
    confirm_email,
    login,
    register_user,
)
from python_coach.transport.deps import (
    AuthConfigDep,
    CurrentUserDep,
    EmailClientDep,
    StorageDep,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    """Registration body — email + plaintext password (validated for length)."""

    email: str
    password: str


class RegisterResponse(BaseModel):
    """Registration result — the account is unconfirmed until the link is followed."""

    email: str
    is_email_confirmed: bool
    message: str


class LoginRequest(BaseModel):
    """Login body — email + plaintext password."""

    email: str
    password: str


class TokenResponse(BaseModel):
    """A minted bearer access token plus its absolute expiry."""

    access_token: str
    token_type: str
    expires_at: datetime


class MeResponse(BaseModel):
    """The current authenticated user."""

    id: int
    email: str
    is_email_confirmed: bool


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    body: RegisterRequest,
    storage: StorageDep,
    email_client: EmailClientDep,
    config: AuthConfigDep,
) -> RegisterResponse:
    """Create an unconfirmed account and send (or log) the confirmation link."""
    try:
        user = await register_user(body.email, body.password, storage, email_client, config)
    except WeakPasswordError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail="email already registered") from exc

    await storage.session.commit()
    return RegisterResponse(
        email=user.email,
        is_email_confirmed=user.is_email_confirmed,
        message="Check your email to confirm your account.",
    )


@router.get("/confirm", response_class=HTMLResponse)
async def confirm(token: str, storage: StorageDep, config: AuthConfigDep) -> HTMLResponse:
    """Verify the confirmation token and present a friendly HTML result page."""
    try:
        await confirm_email(token, storage, config)
    except ConfirmationFailedError as exc:
        await storage.session.rollback()
        return HTMLResponse(_result_page(ok=False, detail=str(exc)), status_code=400)

    await storage.session.commit()
    return HTMLResponse(_result_page(ok=True, detail="Your email is confirmed."))


@router.post("/login", response_model=TokenResponse)
async def login_route(
    body: LoginRequest, storage: StorageDep, config: AuthConfigDep
) -> TokenResponse:
    """Verify credentials against a confirmed account and return an access token."""
    try:
        token = await login(body.email, body.password, storage, config)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="email or password is incorrect") from exc
    except EmailNotConfirmedError as exc:
        raise HTTPException(status_code=403, detail="confirm your email before logging in") from exc

    return TokenResponse(access_token=token.token, token_type="bearer", expires_at=token.expires_at)


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep) -> MeResponse:
    """Return the current user resolved from the bearer token."""
    return MeResponse(id=user.id or 0, email=user.email, is_email_confirmed=user.is_email_confirmed)


def _result_page(ok: bool, detail: str) -> str:
    """Render the minimal confirmation-result HTML (data-testid for QA).

    Heading and detail are escaped so the page is XSS-safe by construction even
    if future callers pass user-controlled strings.
    """
    heading = "Email confirmed" if ok else "Confirmation failed"
    testid = "confirm-result-ok" if ok else "confirm-result-error"
    color = "#1a7f37" if ok else "#cf222e"
    safe_heading = html.escape(heading)
    safe_detail = html.escape(detail)
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>python-coach</title></head>"
        "<body style='font-family: -apple-system, sans-serif; max-width: 480px; "
        "margin: 80px auto; text-align: center;'>"
        f"<h1 style='color: {color};' data-testid='{testid}'>{safe_heading}</h1>"
        f"<p data-testid='confirm-result-detail'>{safe_detail}</p>"
        "<p><a href='/' data-testid='confirm-result-home'>Go to python-coach</a></p>"
        "</body></html>"
    )
