"""Lesson + Exercise read access for Storage.

Surfaces bilingual prose: a lesson is loaded with its exercises, their tests'
ids, and all translation rows eagerly, so the controller can shape a
both-locales payload without N+1 queries. Locale fallback (a missing locale
borrows the other one's prose) is a read-side concern and lives here.
"""

from dataclasses import dataclass

from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from python_coach.storage.models.lesson import (
    SUPPORTED_LOCALES,
    Exercise,
    ExerciseTest,
    Lesson,
)


@dataclass(frozen=True, slots=True)
class LocaleText:
    """One prose field rendered for every supported locale (fallback applied)."""

    by_locale: dict[str, str]


def _resolve_locales(raw: dict[str, str]) -> dict[str, str]:
    """Fill every SUPPORTED_LOCALES key, borrowing prose from a present locale.

    Graceful fallback: if a locale's prose is missing we reuse another present
    locale rather than erroring, so legacy single-locale content still renders.
    """
    present = {loc: text for loc, text in raw.items() if text}
    if not present:
        return {loc: "" for loc in SUPPORTED_LOCALES}
    # Prefer English as the fallback source when available, else any present one.
    fallback = present.get("en") or next(iter(present.values()))
    return {loc: present.get(loc, fallback) for loc in SUPPORTED_LOCALES}


class LessonsMixin:
    """Read-side queries for lessons, exercises and their tests."""

    session: AsyncSession

    async def get_lesson_by_slug(self, slug: str) -> Lesson | None:
        """Fetch one lesson with exercises + all translations eagerly loaded."""
        stmt = (
            select(Lesson)
            .where(Lesson.slug == slug)
            .options(
                selectinload(Lesson.translations),  # type: ignore[arg-type]
                selectinload(Lesson.exercises).selectinload(Exercise.translations),  # type: ignore[arg-type]
            )
        )
        result = await self.session.exec(stmt)
        return result.first()

    @staticmethod
    def lesson_title(lesson: Lesson) -> dict[str, str]:
        """Lesson title per locale, with fallback for any missing locale."""
        return _resolve_locales({t.locale: t.title for t in lesson.translations})

    @staticmethod
    def lesson_body(lesson: Lesson) -> dict[str, str]:
        """Lesson markdown body per locale, with fallback."""
        return _resolve_locales({t.locale: t.body_md for t in lesson.translations})

    @staticmethod
    def exercise_title(exercise: Exercise) -> dict[str, str]:
        """Exercise title per locale, with fallback."""
        return _resolve_locales({t.locale: t.title for t in exercise.translations})

    @staticmethod
    def exercise_statement(exercise: Exercise) -> dict[str, str]:
        """Exercise statement markdown per locale, with fallback."""
        return _resolve_locales({t.locale: t.statement_md for t in exercise.translations})

    async def get_exercise(self, exercise_id: int) -> Exercise | None:
        """Fetch one exercise by id (without tests)."""
        return await self.session.get(Exercise, exercise_id)

    async def get_exercise_tests(self, exercise_id: int) -> list[ExerciseTest]:
        """All test files for an exercise, ordered for deterministic runs."""
        stmt = (
            select(ExerciseTest)
            .where(ExerciseTest.exercise_id == exercise_id)
            .order_by(ExerciseTest.position)  # type: ignore[arg-type]
        )
        result = await self.session.exec(stmt)
        return list(result.all())

    async def list_published_lessons(self) -> list[Lesson]:
        """All published lessons ordered by position, with translations eagerly loaded.

        Only loads the lesson-level translations (title); exercises/tests are not
        fetched — this query is for the curriculum list, not the full lesson view.
        """
        stmt = (
            select(Lesson)
            .where(Lesson.is_published.is_(True))  # type: ignore[union-attr]
            .order_by(Lesson.position)  # type: ignore[arg-type]
            .options(selectinload(Lesson.translations))  # type: ignore[arg-type]
        )
        result = await self.session.exec(stmt)
        return list(result.all())
