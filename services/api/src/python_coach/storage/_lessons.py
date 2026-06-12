"""Lesson + Exercise read access for Storage."""

from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from python_coach.storage.models.lesson import Exercise, ExerciseTest, Lesson


class LessonsMixin:
    """Read-side queries for lessons, exercises and their tests."""

    session: AsyncSession

    async def get_lesson_by_slug(self, slug: str) -> Lesson | None:
        """Fetch one lesson with its ordered exercises eagerly loaded."""
        stmt = (
            select(Lesson).where(Lesson.slug == slug).options(selectinload(Lesson.exercises))  # type: ignore[arg-type]
        )
        result = await self.session.exec(stmt)
        return result.first()

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
