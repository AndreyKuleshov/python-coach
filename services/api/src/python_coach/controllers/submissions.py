"""Submit-and-grade use-case: the core submit -> sandbox -> pytest -> progress flow."""

from dataclasses import dataclass

from python_coach.clients.sandbox import SandboxClient, SandboxFile
from python_coach.clients.sandbox_result import TestRunResult
from python_coach.storage.models.submission import Submission, SubmissionStatus
from python_coach.storage.storage import Storage


@dataclass(frozen=True, slots=True)
class GradeOutcome:
    """Result of grading one submission: the persisted row plus solved flag."""

    submission: Submission
    solved: bool


class ExerciseNotFoundError(Exception):
    """Raised when a submission targets an exercise that does not exist."""


async def submit_solution(
    user_id: int,
    exercise_id: int,
    code: str,
    storage: Storage,
    sandbox: SandboxClient,
) -> GradeOutcome:
    """Grade user `code` for an exercise in the sandbox and record per-user progress."""
    exercise = await storage.get_exercise(exercise_id)
    if exercise is None:
        raise ExerciseNotFoundError(exercise_id)

    tests = await storage.get_exercise_tests(exercise_id)

    submission = await storage.create_pending_submission(user_id, exercise_id, code)

    # Run the (possibly hostile) code in the isolated container.
    solution_file = SandboxFile(name=f"{exercise.solution_module}.py", content=code)
    test_files = [SandboxFile(name=t.filename, content=t.content) for t in tests]
    result = await sandbox.run(solution=solution_file, tests=test_files)

    status = _status_from_result(result)
    submission = await storage.finalize_submission(submission, status, result)

    # An infrastructure failure (timeout/crash/OOM) is not the user's fault: we
    # persist the ERROR/TIMEOUT submission row but do NOT count it as an attempt.
    if result.runner_error:
        return GradeOutcome(submission=submission, solved=False)

    solved = status == SubmissionStatus.PASSED
    await storage.record_attempt(user_id, exercise_id, submission.id or 0, solved=solved)
    return GradeOutcome(submission=submission, solved=solved)


def _status_from_result(result: TestRunResult) -> SubmissionStatus:
    """Map a sandbox run into a submission lifecycle status."""
    if result.runner_error:
        # Distinguish a wall-clock kill from other runner failures for the UI.
        if "wall-clock" in result.runner_error:
            return SubmissionStatus.TIMEOUT
        return SubmissionStatus.ERROR
    return SubmissionStatus.PASSED if result.passed else SubmissionStatus.FAILED


async def get_submission(user_id: int, submission_id: int, storage: Storage) -> Submission | None:
    """Fetch a graded submission by id, scoped to its owner (no cross-user reads)."""
    submission = await storage.get_submission(submission_id)
    if submission is None or submission.user_id != user_id:
        return None
    return submission
