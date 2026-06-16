"""Submission + Progress ORM tables.

A Submission is one attempt by one user at one exercise (the user's code + the
structured pytest result). Progress is the per-(user, exercise) roll-up used to
render the UI. Both reference the `user` table by FK — progress is per account.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(UTC)


def _tz_column(*, index: bool = False) -> Column:
    """A TIMESTAMP WITH TIME ZONE column; index applied on the column directly."""
    return Column(DateTime(timezone=True), index=index)


class SubmissionStatus(StrEnum):
    """Lifecycle of a single submission run."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"  # sandbox/runner failure, not a test failure
    TIMEOUT = "timeout"


class Submission(SQLModel, table=True):
    """One graded attempt: stores the submitted code and the structured verdict."""

    __tablename__ = "submission"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    # Deleting a user removes their submissions (cascade).
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    # Re-ingesting a lesson deletes its exercises and (by cascade) their submissions.
    exercise_id: int = Field(foreign_key="exercise.id", index=True, ondelete="CASCADE")
    code: str
    status: SubmissionStatus = Field(default=SubmissionStatus.PENDING, index=True)
    # Structured pytest result (TestRunResult serialized) — JSONB for queryability.
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column(index=True))


class Progress(SQLModel, table=True):
    """Per-(user, exercise) progress roll-up: solved-or-not plus attempt counters."""

    __tablename__ = "progress"  # type: ignore[assignment]
    # Progress is tracked per account: one row per (user, exercise) pair.
    __table_args__ = (UniqueConstraint("user_id", "exercise_id", name="uq_progress_user_exercise"),)

    id: int | None = Field(default=None, primary_key=True)
    # Deleting a user removes their progress (cascade).
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    exercise_id: int = Field(foreign_key="exercise.id", index=True, ondelete="CASCADE")
    is_solved: bool = Field(default=False)
    attempts: int = Field(default=0)
    # SET NULL: a submission can vanish (cascade) while the progress row survives.
    last_submission_id: int | None = Field(
        default=None, foreign_key="submission.id", ondelete="SET NULL"
    )
    solved_at: datetime | None = Field(default=None, sa_column=_tz_column())
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
