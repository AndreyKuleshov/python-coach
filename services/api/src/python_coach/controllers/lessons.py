"""Lesson read use-cases.

Produces a both-locales view: every prose field carries one string per
supported locale so the frontend can switch language client-side with no
re-fetch. Code-bearing fields and hidden test sources / solution_code are NOT
part of this view — the route shapes only what the learner may see.
"""

from dataclasses import dataclass

from python_coach.storage.storage import Storage


@dataclass(frozen=True, slots=True)
class ExerciseView:
    """One exercise as the lesson page needs it: bilingual prose + starter code.

    `title` / `statement_md` are dicts keyed by locale ("en"/"ru"). No tests,
    no solution_code — those never reach the frontend.
    """

    id: int
    slug: str
    title: dict[str, str]
    statement_md: dict[str, str]
    starter_code: str


@dataclass(frozen=True, slots=True)
class LessonView:
    """A lesson plus its ordered exercises, both locales, ready to shape."""

    id: int
    slug: str
    is_published: bool
    title: dict[str, str]
    body_md: dict[str, str]
    exercises: list[ExerciseView]


async def get_lesson(slug: str, storage: Storage) -> LessonView | None:
    """Load a lesson by slug for rendering; None when it does not exist."""
    lesson = await storage.get_lesson_by_slug(slug)
    if lesson is None:
        return None

    exercises = [
        ExerciseView(
            id=ex.id or 0,
            slug=ex.slug,
            title=storage.exercise_title(ex),
            statement_md=storage.exercise_statement(ex),
            starter_code=ex.starter_code,
        )
        for ex in lesson.exercises
    ]
    return LessonView(
        id=lesson.id or 0,
        slug=lesson.slug,
        is_published=lesson.is_published,
        title=storage.lesson_title(lesson),
        body_md=storage.lesson_body(lesson),
        exercises=exercises,
    )
