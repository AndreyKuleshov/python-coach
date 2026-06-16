"""Auth use-cases: register, confirm email, login, resolve current user.

Orchestrates Storage (the user table), the EmailClient (confirmation link), and
the pure crypto helpers in controllers/security.py. Never imports fastapi —
the route maps these outcomes / exceptions to HTTP.
"""

from dataclasses import dataclass

from python_coach.clients.email import EmailClient
from python_coach.controllers.security import (
    AccessToken,
    InvalidTokenError,
    hash_password,
    mint_access_token,
    mint_confirm_token,
    read_confirm_token,
    verify_password,
)
from python_coach.storage.models.user import User
from python_coach.storage.storage import Storage

# Minimal password policy: enough to reject obviously weak input without a
# full strength meter (deferred to a later stage).
_MIN_PASSWORD_LENGTH = 8


class EmailAlreadyRegisteredError(Exception):
    """Raised when registering an email that already has an account."""


class WeakPasswordError(Exception):
    """Raised when a registration password fails the minimal policy."""


class InvalidCredentialsError(Exception):
    """Raised when login email/password do not match a confirmed account."""


class EmailNotConfirmedError(Exception):
    """Raised when login is attempted before the email is confirmed."""


class ConfirmationFailedError(Exception):
    """Raised when an email-confirmation token is invalid/expired or its user is gone."""


@dataclass(frozen=True, slots=True)
class AuthConfig:
    """JWT knobs threaded from settings into the auth use-cases."""

    secret: str
    access_token_minutes: int
    confirm_token_minutes: int
    public_base_url: str


def _normalize_email(email: str) -> str:
    """Lower-case + trim so the unique constraint is case-insensitive."""
    return email.strip().lower()


async def register_user(
    email: str,
    password: str,
    storage: Storage,
    email_client: EmailClient,
    config: AuthConfig,
) -> User:
    """Create an unconfirmed account and send (or log) the confirmation link."""
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"password must be at least {_MIN_PASSWORD_LENGTH} characters")

    normalized = _normalize_email(email)
    existing = await storage.get_user_by_email(normalized)
    if existing is not None:
        raise EmailAlreadyRegisteredError(normalized)

    user = await storage.create_user(normalized, hash_password(password))

    # Signed confirmation token -> no token table; verified on /confirm.
    token = mint_confirm_token(user.id or 0, config.secret, config.confirm_token_minutes)
    confirm_url = f"{config.public_base_url}/api/auth/confirm?token={token}"
    await email_client.send_confirmation(user.email, confirm_url)
    return user


async def confirm_email(token: str, storage: Storage, config: AuthConfig) -> User:
    """Verify a confirmation token and flip the user's email-confirmed flag."""
    try:
        user_id = read_confirm_token(token, config.secret)
    except InvalidTokenError as exc:
        raise ConfirmationFailedError("invalid or expired confirmation link") from exc

    user = await storage.get_user_by_id(user_id)
    if user is None:
        raise ConfirmationFailedError("account no longer exists")
    if user.is_email_confirmed:
        return user
    return await storage.mark_email_confirmed(user)


async def login(
    email: str,
    password: str,
    storage: Storage,
    config: AuthConfig,
) -> AccessToken:
    """Verify credentials against a confirmed account and mint an access token."""
    normalized = _normalize_email(email)
    user = await storage.get_user_by_email(normalized)
    # Verify even when the user is missing-ish to keep the failure shape uniform;
    # but a missing user has no hash, so guard first.
    if user is None or not verify_password(user.password_hash, password):
        raise InvalidCredentialsError("email or password is incorrect")
    if not user.is_email_confirmed:
        raise EmailNotConfirmedError("confirm your email before logging in")

    return mint_access_token(user.id or 0, config.secret, config.access_token_minutes)
