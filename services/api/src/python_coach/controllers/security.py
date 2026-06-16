"""Password hashing (Argon2id) + JWT minting/verification helpers.

These are pure-CPU use-case utilities (no external upstream, no fastapi), so
they sit in the controllers layer alongside the auth use-cases that call them.
Two JWT purposes share one signing secret, distinguished by a `purpose` claim:
  - "access"  — the bearer session token returned by login.
  - "confirm" — the short-lived email-confirmation token (no token table needed).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_PURPOSE_ACCESS = "access"
_PURPOSE_CONFIRM = "confirm"
_ALGORITHM = "HS256"

# argon2-cffi defaults are Argon2id with sensible cost params; one shared
# instance is safe to reuse across requests.
_hasher = PasswordHasher()


class InvalidTokenError(Exception):
    """Raised when a JWT is malformed, expired, or has the wrong purpose."""


@dataclass(frozen=True, slots=True)
class AccessToken:
    """A minted access token plus its absolute expiry (for the response DTO)."""

    token: str
    expires_at: datetime


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2id for at-rest storage."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Check a plaintext password against a stored Argon2 hash."""
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def mint_access_token(user_id: int, secret: str, lifetime_minutes: int) -> AccessToken:
    """Mint a signed bearer access token carrying the user id."""
    expires_at = datetime.now(UTC) + timedelta(minutes=lifetime_minutes)
    payload = {"sub": str(user_id), "purpose": _PURPOSE_ACCESS, "exp": expires_at}
    token = jwt.encode(payload, secret, algorithm=_ALGORITHM)
    return AccessToken(token=token, expires_at=expires_at)


def mint_confirm_token(user_id: int, secret: str, lifetime_minutes: int) -> str:
    """Mint a short-lived signed token for email confirmation (no DB token row)."""
    expires_at = datetime.now(UTC) + timedelta(minutes=lifetime_minutes)
    payload = {"sub": str(user_id), "purpose": _PURPOSE_CONFIRM, "exp": expires_at}
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def read_access_token(token: str, secret: str) -> int:
    """Verify an access token and return its user id."""
    return _decode_for_purpose(token, secret, _PURPOSE_ACCESS)


def read_confirm_token(token: str, secret: str) -> int:
    """Verify a confirmation token and return its user id."""
    return _decode_for_purpose(token, secret, _PURPOSE_CONFIRM)


def _decode_for_purpose(token: str, secret: str, purpose: str) -> int:
    """Decode a JWT, enforce the expected purpose claim, return the user id."""
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("invalid or expired token") from exc

    if payload.get("purpose") != purpose:
        raise InvalidTokenError("token has the wrong purpose")
    sub = payload.get("sub")
    if sub is None:
        raise InvalidTokenError("token missing subject")
    # Guard against a forged-but-signed token whose `sub` is a non-numeric string:
    # int() would raise ValueError and bubble as a 500; normalise it to a clean 401.
    try:
        return int(sub)
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError("token subject is not a valid user id") from exc
