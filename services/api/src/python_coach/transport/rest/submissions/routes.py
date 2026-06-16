"""Submit-solution + get-result endpoints and their DTOs."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from python_coach.controllers.lessons import LessonLockedError
from python_coach.controllers.submissions import (
    ExerciseNotFoundError,
    get_submission,
    submit_solution,
)
from python_coach.storage.models.submission import Submission, SubmissionStatus
from python_coach.transport.deps import CurrentUserDep, SandboxDep, StorageDep

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


class SubmitRequest(BaseModel):
    """Body for submitting a solution attempt."""

    exercise_id: int
    code: str


class TestResultDTO(BaseModel):
    """Per-test outcome surfaced to the results panel."""

    name: str
    outcome: str
    duration_seconds: float
    message: str


class SubmissionDTO(BaseModel):
    """A graded submission: status + structured per-test results."""

    id: int
    exercise_id: int
    status: SubmissionStatus
    passed: bool
    total: int
    passed_count: int
    failed_count: int
    tests: list[TestResultDTO]
    runner_error: str
    stderr: str


def _to_dto(submission: Submission) -> SubmissionDTO:
    """Shape a persisted submission (+ its JSON result) into the response DTO."""
    result = submission.result or {}
    tests = [
        TestResultDTO(
            name=t["name"],
            outcome=t["outcome"],
            duration_seconds=t.get("duration_seconds", 0.0),
            message=t.get("message", ""),
        )
        for t in result.get("tests", [])
    ]
    return SubmissionDTO(
        id=submission.id or 0,
        exercise_id=submission.exercise_id,
        status=submission.status,
        passed=bool(result.get("passed", False)),
        total=result.get("total", 0),
        passed_count=result.get("passed_count", 0),
        failed_count=result.get("failed_count", 0),
        tests=tests,
        runner_error=result.get("runner_error", ""),
        stderr=result.get("stderr", ""),
    )


@router.post("", response_model=SubmissionDTO)
async def create_submission(
    body: SubmitRequest, user: CurrentUserDep, storage: StorageDep, sandbox: SandboxDep
) -> SubmissionDTO:
    """Grade a solution in the sandbox (for the current user) and return the verdict."""
    try:
        # Controller takes unpacked primitives, not the DTO instance.
        outcome = await submit_solution(user.id or 0, body.exercise_id, body.code, storage, sandbox)
    except ExerciseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="exercise not found") from exc
    except LessonLockedError as exc:
        raise HTTPException(status_code=403, detail="lesson is locked") from exc

    await storage.session.commit()
    return _to_dto(outcome.submission)


@router.get("/{submission_id}", response_model=SubmissionDTO)
async def read_submission(
    submission_id: int, user: CurrentUserDep, storage: StorageDep
) -> SubmissionDTO:
    """Fetch one of the current user's graded submissions by id."""
    submission = await get_submission(user.id or 0, submission_id, storage)
    if submission is None:
        raise HTTPException(status_code=404, detail="submission not found")
    return _to_dto(submission)
