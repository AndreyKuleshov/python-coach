"""Lesson read use-cases.

Produces a both-locales view: every prose field carries one string per
supported locale so the frontend can switch language client-side with no
re-fetch. Code-bearing fields and hidden test sources / solution_code are NOT
part of this view — the route shapes only what the learner may see.
"""

from dataclasses import dataclass

from python_coach.storage._lessons import LessonExerciseCounts
from python_coach.storage.models.lesson import Lesson
from python_coach.storage.storage import Storage


@dataclass(frozen=True, slots=True)
class LessonState:
    """Derived per-user state of one published lesson in the ordered curriculum.

    `is_completed` is derived (lesson has exercises AND the user solved them all).
    `is_unlocked` follows sequential-unlock: the first published lesson is always
    unlocked; any later one is unlocked iff the immediately-preceding published
    lesson is completed by the user.
    """

    lesson: Lesson
    total_exercises: int
    solved_exercises: int
    is_completed: bool
    is_unlocked: bool


def _is_completed(counts: LessonExerciseCounts | None) -> bool:
    """A lesson is completed only when it has exercises and the user solved them all."""
    if counts is None or counts.total_exercises == 0:
        return False
    return counts.solved_exercises >= counts.total_exercises


def _compute_states(
    lessons: list[Lesson], counts_by_lesson: dict[int, LessonExerciseCounts]
) -> list[LessonState]:
    """Fold completion + sequential-unlock over the position-ordered published lessons.

    `lessons` must already be ordered by position. Unlock is a running flag: the
    first lesson is unlocked; each subsequent lesson inherits unlocked iff the
    previous lesson was completed.
    """
    states: list[LessonState] = []
    prev_completed = True  # the first lesson is always unlocked
    for lesson in lessons:
        counts = counts_by_lesson.get(lesson.id or 0)
        completed = _is_completed(counts)
        states.append(
            LessonState(
                lesson=lesson,
                total_exercises=counts.total_exercises if counts else 0,
                solved_exercises=counts.solved_exercises if counts else 0,
                is_completed=completed,
                is_unlocked=prev_completed,
            )
        )
        prev_completed = completed
    return states


async def get_lesson_states(user_id: int, storage: Storage) -> list[LessonState]:
    """Published lessons (ordered) with per-user completion + unlock derived."""
    lessons = await storage.list_published_lessons()
    counts = await storage.exercise_counts_by_lesson(user_id)
    return _compute_states(lessons, counts)


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
    """A lesson plus its ordered exercises, both locales, ready to shape.

    Carries the per-user `is_completed` flag and `next_slug` (next published
    lesson by position, or None when this is the last) so the lesson view can
    render the completed state and the "Next lesson" button without a re-fetch.
    """

    id: int
    slug: str
    is_published: bool
    title: dict[str, str]
    body_md: dict[str, str]
    exercises: list[ExerciseView]
    is_completed: bool
    next_slug: str | None


@dataclass(frozen=True, slots=True)
class LessonSummary:
    """Minimal curriculum entry — just enough for a list row.

    Deliberately excludes body, exercises, tests, and solution_code so the
    list payload is safe to expose without anti-cheat concerns. Carries the
    derived per-user `is_completed` / `is_unlocked` so the list can gate rows.
    """

    slug: str
    title: dict[str, str]
    position: int
    is_completed: bool
    is_unlocked: bool


class LessonLockedError(Exception):
    """Raised when a user tries to read a lesson that is locked for them."""


async def list_published_lessons(user_id: int, storage: Storage) -> list[LessonSummary]:
    """Published lesson summaries (ordered) with per-user completion + unlock state."""
    states = await get_lesson_states(user_id, storage)
    return [
        LessonSummary(
            slug=state.lesson.slug,
            title=storage.lesson_title(state.lesson),
            position=state.lesson.position,
            is_completed=state.is_completed,
            is_unlocked=state.is_unlocked,
        )
        for state in states
    ]


async def get_lesson(slug: str, user_id: int, storage: Storage) -> LessonView | None:
    """Load a lesson by slug for the user; None when missing, raise when locked.

    Locking is enforced here (the real server-side gate): a lesson the user has
    not unlocked never has its content shaped — the route maps the raised
    LessonLockedError to a 403.
    """
    lesson = await storage.get_lesson_by_slug(slug)
    if lesson is None:
        return None

    # Compute the curriculum states once: they drive the lock check, the
    # completed flag, and the next-lesson pointer.
    states = await get_lesson_states(user_id, storage)
    state = next((s for s in states if s.lesson.id == lesson.id), None)

    # Only PUBLISHED lessons participate in the unlock chain. An unpublished
    # lesson is not in `states`; it is still directly addressable (e.g. preview)
    # and treated as unlocked/incomplete.
    if state is not None and not state.is_unlocked:
        raise LessonLockedError(slug)

    next_slug = _next_slug(states, lesson.id or 0)

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
        is_completed=state.is_completed if state is not None else False,
        next_slug=next_slug,
    )


def _next_slug(states: list[LessonState], lesson_id: int) -> str | None:
    """Slug of the published lesson right after `lesson_id` by position, else None."""
    for index, state in enumerate(states):
        if state.lesson.id != lesson_id:
            continue
        nxt = index + 1
        return states[nxt].lesson.slug if nxt < len(states) else None
    return None
