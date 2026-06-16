"""Profile/progress aggregate use-case.

Produces the personal-cabinet view: the user's email plus an ordered list of all
published lessons with per-user completion/unlock state and solved/total counts,
plus the lessons-completed / lessons-total totals. Reuses the lessons
controller's curriculum-state fold so completion + sequential unlock stay
defined in exactly one place.
"""

from dataclasses import dataclass

from python_coach.controllers.lessons import get_lesson_states
from python_coach.storage.storage import Storage


@dataclass(frozen=True, slots=True)
class ProfileLesson:
    """One published lesson as the profile page needs it: bilingual title + counts."""

    slug: str
    title: dict[str, str]
    position: int
    total_exercises: int
    solved_exercises: int
    is_completed: bool
    is_unlocked: bool


@dataclass(frozen=True, slots=True)
class Profile:
    """The personal-cabinet aggregate: identity + per-lesson progress + totals."""

    email: str
    lessons: list[ProfileLesson]
    lessons_completed: int
    lessons_total: int


async def get_profile(user_id: int, email: str, storage: Storage) -> Profile:
    """Aggregate the current user's progress across all published lessons."""
    states = await get_lesson_states(user_id, storage)
    lessons = [
        ProfileLesson(
            slug=state.lesson.slug,
            title=storage.lesson_title(state.lesson),
            position=state.lesson.position,
            total_exercises=state.total_exercises,
            solved_exercises=state.solved_exercises,
            is_completed=state.is_completed,
            is_unlocked=state.is_unlocked,
        )
        for state in states
    ]
    return Profile(
        email=email,
        lessons=lessons,
        lessons_completed=sum(1 for state in states if state.is_completed),
        lessons_total=len(states),
    )
