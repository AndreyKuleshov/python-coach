"""Exercise endpoints and their response DTOs.

Currently exposes a single endpoint: GET /api/exercises/{exercise_id}/solution,
which reveals the hidden reference solution only after the user has solved the
exercise. All other lesson/exercise content is served by the lessons router.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from python_coach.controllers.exercises import (
    ExerciseNotFoundError,
    NoReferenceSolutionError,
    NotSolvedError,
    get_exercise_solution,
)
from python_coach.controllers.lessons import LessonLockedError
from python_coach.transport.deps import CurrentUserDep, StorageDep

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


class SolutionDTO(BaseModel):
    """The reference solution revealed to a user who has solved the exercise."""

    solution_code: str


@router.get("/{exercise_id}/solution", response_model=SolutionDTO)
async def read_exercise_solution(
    exercise_id: int, user: CurrentUserDep, storage: StorageDep
) -> SolutionDTO:
    """Reveal the reference solution for an exercise the current user has solved.

    Authorization:
      - 401: no/invalid bearer token (handled by CurrentUserDep).
      - 404: exercise not found, or no reference solution stored.
      - 403: lesson is locked for the user, or the user has not solved the exercise.
      - 200 + solution_code: the user has a solved Progress row for this exercise.

    The lesson list/detail endpoints NEVER include solution_code — this is the
    only path to read it, and only post-solve per the anti-cheat contract.
    """
    try:
        result = await get_exercise_solution(user.id or 0, exercise_id, storage)
    except ExerciseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="exercise not found") from exc
    except LessonLockedError as exc:
        raise HTTPException(status_code=403, detail="lesson is locked") from exc
    except NotSolvedError as exc:
        raise HTTPException(
            status_code=403, detail="solve the exercise first to reveal the reference solution"
        ) from exc
    except NoReferenceSolutionError as exc:
        raise HTTPException(status_code=404, detail="no reference solution available") from exc

    return SolutionDTO(solution_code=result.solution_code)
