"""Lesson + Exercise + ExerciseTest ORM tables (SQLModel doubles as domain model).

Relationships encoded here: one Lesson -> many Exercise -> many ExerciseTest.
A lesson with zero exercises is "incomplete" content (enforced in the
controller / contract, not by the DB) but is allowed to exist as a skeleton.

Localisation model: learner-facing PROSE is bilingual (en + ru) and lives in
side tables `lesson_translation` / `exercise_translation` keyed by
(entity_id, locale). Code-bearing fields (starter_code, solution_code,
solution_module, each test's filename/content/is_hidden) are language-neutral
and stay single-valued on the base tables — code is code; pytest names and
messages are not translated.
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

# The two concrete locales the platform ships. A third would be a schema-free
# addition (just more translation rows), but the product requires both today.
SUPPORTED_LOCALES = ("en", "ru")


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
    # Display order within the curriculum.
    position: int = Field(default=0, index=True)
    # Placeholder fixtures set this False; real methodist content sets True.
    is_published: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())

    exercises: list["Exercise"] = Relationship(
        back_populates="lesson",
        sa_relationship_kwargs={"order_by": "Exercise.position", "cascade": "all, delete-orphan"},
    )
    # Per-locale prose (title + body_md). One row per (lesson, locale).
    translations: list["LessonTranslation"] = Relationship(
        back_populates="lesson",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class LessonTranslation(SQLModel, table=True):
    """Per-locale prose for a lesson (title + markdown body)."""

    __tablename__ = "lesson_translation"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("lesson_id", "locale", name="uq_lesson_translation_locale"),)

    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True, ondelete="CASCADE")
    # One of SUPPORTED_LOCALES ("en" | "ru"); not an enum so adding a locale is data-only.
    locale: str = Field(index=True)
    title: str
    # Markdown lesson text rendered verbatim by the frontend.
    body_md: str

    lesson: Lesson = Relationship(back_populates="translations")


class Exercise(SQLModel, table=True):
    """A single coding task inside a lesson, checked by one-or-many pytest tests."""

    __tablename__ = "exercise"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    # DB-level cascade so a bulk lesson delete (re-ingest) removes its exercises.
    lesson_id: int = Field(foreign_key="lesson.id", index=True, ondelete="CASCADE")
    # Unique within a lesson; combined with lesson slug it is globally addressable.
    slug: str = Field(index=True)
    # Pre-filled editor content. Empty string = blank editor.
    starter_code: str = Field(default="")
    # Hidden reference solution used to self-validate the tests. NEVER exposed by
    # the lesson API (same secrecy class as hidden test sources). Optional.
    solution_code: str | None = Field(default=None)
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
    # Per-locale prose (title + statement_md). One row per (exercise, locale).
    translations: list["ExerciseTranslation"] = Relationship(
        back_populates="exercise",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ExerciseTranslation(SQLModel, table=True):
    """Per-locale prose for an exercise (title + markdown statement)."""

    __tablename__ = "exercise_translation"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("exercise_id", "locale", name="uq_exercise_translation_locale"),
    )

    id: int | None = Field(default=None, primary_key=True)
    exercise_id: int = Field(foreign_key="exercise.id", index=True, ondelete="CASCADE")
    locale: str = Field(index=True)
    title: str
    # Markdown task statement shown above the editor.
    statement_md: str

    exercise: Exercise = Relationship(back_populates="translations")


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
