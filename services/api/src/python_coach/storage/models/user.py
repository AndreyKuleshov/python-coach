"""User ORM table (SQLModel doubles as domain model).

A single registered account. Login is by email (stored lower-cased so the
unique constraint is case-insensitive without needing the citext extension).
Email must be confirmed (via a signed confirmation token) before login is
allowed. Per-user progress/submissions reference this table by FK.
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Timezone-aware UTC now — stored as tz-aware timestamps everywhere."""
    return datetime.now(UTC)


def _tz_column() -> Column:
    """A TIMESTAMP WITH TIME ZONE column (asyncpg rejects tz-aware into naive)."""
    return Column(DateTime(timezone=True))


class User(SQLModel, table=True):
    """A registered learner account: email login + Argon2 password hash."""

    __tablename__ = "user"  # type: ignore[assignment]  # SQLModel/pyright stub friction

    id: int | None = Field(default=None, primary_key=True)
    # Lower-cased at the controller boundary so uniqueness is case-insensitive.
    email: str = Field(index=True, unique=True)
    # Argon2id hash (argon2-cffi). Never the plaintext password.
    password_hash: str
    # Login is rejected until the confirmation link is followed.
    is_email_confirmed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
