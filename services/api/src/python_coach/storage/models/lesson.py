"""Lesson + Exercise + ExerciseTest ORM tables (SQLModel doubles as domain model).

Relationships encoded here: one Lesson -> many Exercise -> many ExerciseTest.
A lesson with zero exercises is "incomplete" content (enforced in the
controller / contract, not by the DB) but is allowed to exist as a skeleton.
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime
from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    """Timezone-aware UTC now — stored as tz-aware timestamps everywhere."""
    return datetime.now(UTC)


def _tz_column() -> Column:
    """A TIMESTAMP WITH TIME ZONE column (asyncpg rejects tz-aware into naive)."""
    return Column(DateTime(timezone=True))


class Lesson(SQLModel, table=True):
    """A unit of learning: markdown body + an ordered list of exercises."""

    __tablename__ = "lesson"  # type: ignore[assignment]  # SQLModel/pyright stub friction

    id: int | None = Field(default=None, primary_key=True)
    # Stable human/author-facing identifier used by the ingest format.
    slug: str = Field(index=True, unique=True)
    title: str
    # Markdown lesson text rendered verbatim by the frontend.
    body_md: str
    # Display order within the curriculum.
    position: int = Field(default=0, index=True)
    # Placeholder fixtures set this False; real methodist content sets True.
    is_published: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())

    exercises: list["Exercise"] = Relationship(
        back_populates="lesson",
        sa_relationship_kwargs={"order_by": "Exercise.position", "cascade": "all, delete-orphan"},
    )


class Exercise(SQLModel, table=True):
    """A single coding task inside a lesson, checked by one-or-many pytest tests."""

    __tablename__ = "exercise"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    # DB-level cascade so a bulk lesson delete (re-ingest) removes its exercises.
    lesson_id: int = Field(foreign_key="lesson.id", index=True, ondelete="CASCADE")
    # Unique within a lesson; combined with lesson slug it is globally addressable.
    slug: str = Field(index=True)
    title: str
    # Markdown task statement shown above the editor.
    statement_md: str
    # Pre-filled editor content. Empty string = blank editor.
    starter_code: str = Field(default="")
    # Name the user's submitted module is saved as inside the sandbox, so tests
    # can `from solution import ...`. Kept per-exercise for flexibility.
    solution_module: str = Field(default="solution")
    position: int = Field(default=0, index=True)

    lesson: Lesson = Relationship(back_populates="exercises")
    tests: list["ExerciseTest"] = Relationship(
        back_populates="exercise",
        sa_relationship_kwargs={
            "order_by": "ExerciseTest.position",
            "cascade": "all, delete-orphan",
        },
    )


class ExerciseTest(SQLModel, table=True):
    """One pytest test file for an exercise (an exercise has one or many)."""

    __tablename__ = "exercise_test"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    exercise_id: int = Field(foreign_key="exercise.id", index=True, ondelete="CASCADE")
    # File name written into the sandbox; must match pytest discovery (test_*.py).
    filename: str
    # Full pytest source. May `from solution import ...` (Exercise.solution_module).
    content: str = Field(default="")
    # Hidden tests are run but their source is never sent to the frontend.
    is_hidden: bool = Field(default=False)
    position: int = Field(default=0)

    exercise: Exercise = Relationship(back_populates="tests")
