"""AI use-cases: on-the-fly exercise hints and lesson-excerpt explanations.

Orchestrates `storage` (to find the exercise and enforce the lesson lock) and the
`LLMClient`. Never imports fastapi. The hint use-case deliberately passes only the
PUBLIC statement + starter code to the model — never the hidden `solution_code` —
so the reference solution cannot leak through a hint.
"""

from python_coach.clients.llm import LLMClient
from python_coach.controllers.lessons import LessonLockedError, get_lesson_states
from python_coach.controllers.submissions import ExerciseNotFoundError
from python_coach.storage.storage import Storage


class AIDisabledError(Exception):
    """Raised when an AI use-case is hit while no OpenAI key is configured."""


async def generate_hint(
    user_id: int,
    exercise_id: int,
    locale: str,
    storage: Storage,
    llm: LLMClient,
) -> str:
    """An approach hint for an exercise the user is allowed to see.

    Gating mirrors submissions: a hint for an exercise in a locked lesson is
    refused (LessonLockedError -> 403). The hidden solution_code is never read
    here, so it cannot reach the model.
    """
    if not llm.is_enabled:
        raise AIDisabledError

    exercise = await storage.get_exercise_with_translations(exercise_id)
    if exercise is None:
        raise ExerciseNotFoundError(exercise_id)

    # Gate: the exercise's PUBLISHED lesson must be unlocked for this user.
    states = await get_lesson_states(user_id, storage)
    lesson_state = next((s for s in states if s.lesson.id == exercise.lesson_id), None)
    if lesson_state is not None and not lesson_state.is_unlocked:
        raise LessonLockedError(exercise.lesson_id)

    statement = storage.exercise_statement(exercise).get(locale, "")
    return await llm.hint(statement=statement, starter_code=exercise.starter_code, locale=locale)


async def explain_excerpt(excerpt: str, question: str, locale: str, llm: LLMClient) -> str:
    """Explain a pasted lesson excerpt in more detail, in the UI locale."""
    if not llm.is_enabled:
        raise AIDisabledError
    return await llm.explain(excerpt=excerpt, question=question, locale=locale)
