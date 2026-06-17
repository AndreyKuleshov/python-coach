"""Exercise-level use-cases that are not part of the submission/grading flow.

Currently hosts the reference-solution reveal: a post-solve unlock that exposes
the hidden solution_code column only once the user has a solved Progress row for
the exercise. The lesson API never exposes solution_code — this is the only
controlled path to read it.
"""

from dataclasses import dataclass

from python_coach.controllers.lessons import LessonLockedError, get_lesson_states
from python_coach.storage.storage import Storage


class ExerciseNotFoundError(Exception):
    """Raised when the requested exercise does not exist in the database."""


class NotSolvedError(Exception):
    """Raised when the user has not yet solved the exercise (solution gated)."""


class NoReferenceSolutionError(Exception):
    """Raised when the exercise has no (non-blank) reference solution stored."""


@dataclass(frozen=True, slots=True)
class SolutionResult:
    """The revealed reference solution for one exercise."""

    solution_code: str


async def get_exercise_solution(
    user_id: int,
    exercise_id: int,
    storage: Storage,
) -> SolutionResult:
    """Return the reference solution iff the user has solved the exercise.

    Authorization chain (outermost to innermost):
      1. Exercise must exist — 404 otherwise.
      2. The exercise's published lesson must be unlocked for the user — 403
         (LessonLockedError) if locked. An unpublished lesson is treated as
         unlocked (same rule as the lesson-read controller).
      3. The user must have a solved Progress row for this exercise — 403
         (NotSolvedError) if they haven't passed yet.
      4. The exercise must have a non-blank solution_code stored — 404
         (NoReferenceSolutionError) if the methodist left it blank.
    """
    exercise = await storage.get_exercise(exercise_id)
    if exercise is None:
        raise ExerciseNotFoundError(exercise_id)

    # Gate: locked lesson → 403. Mirrors the submissions controller.
    states = await get_lesson_states(user_id, storage)
    lesson_state = next((s for s in states if s.lesson.id == exercise.lesson_id), None)
    if lesson_state is not None and not lesson_state.is_unlocked:
        raise LessonLockedError(exercise.lesson_id)

    # Gate: solution is only readable after the user has passed the exercise.
    progress = await storage.get_progress(user_id, exercise_id)
    if progress is None or not progress.is_solved:
        raise NotSolvedError(exercise_id)

    code = await storage.get_exercise_solution_code(exercise_id)
    if code is None:
        raise NoReferenceSolutionError(exercise_id)

    return SolutionResult(solution_code=code)
