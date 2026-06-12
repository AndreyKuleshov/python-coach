"""Progress read endpoint and its DTO."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from python_coach.controllers.progress import get_progress
from python_coach.transport.deps import StorageDep

router = APIRouter(prefix="/api/progress", tags=["progress"])


class ProgressDTO(BaseModel):
    """Per-exercise progress roll-up; not-yet-attempted exercises report zeros."""

    exercise_id: int
    is_solved: bool
    attempts: int
    last_submission_id: int | None
    solved_at: datetime | None


@router.get("/{exercise_id}", response_model=ProgressDTO)
async def read_progress(exercise_id: int, storage: StorageDep) -> ProgressDTO:
    """Return progress for an exercise; zeros when there has been no attempt."""
    progress = await get_progress(exercise_id, storage)
    if progress is None:
        return ProgressDTO(
            exercise_id=exercise_id,
            is_solved=False,
            attempts=0,
            last_submission_id=None,
            solved_at=None,
        )
    return ProgressDTO(
        exercise_id=progress.exercise_id,
        is_solved=progress.is_solved,
        attempts=progress.attempts,
        last_submission_id=progress.last_submission_id,
        solved_at=progress.solved_at,
    )
