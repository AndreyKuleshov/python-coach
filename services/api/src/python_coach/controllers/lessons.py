"""Lesson read use-cases."""

from dataclasses import dataclass

from python_coach.storage.models.lesson import Exercise, Lesson
from python_coach.storage.storage import Storage


@dataclass(frozen=True, slots=True)
class LessonView:
    """A lesson plus its ordered exercises, ready for the route to shape."""

    lesson: Lesson
    exercises: list[Exercise]


async def get_lesson(slug: str, storage: Storage) -> LessonView | None:
    """Load a lesson by slug for rendering; None when it does not exist."""
    lesson = await storage.get_lesson_by_slug(slug)
    if lesson is None:
        return None
    return LessonView(lesson=lesson, exercises=list(lesson.exercises))
