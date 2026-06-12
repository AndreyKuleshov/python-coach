"""Submission write/read access for Storage."""

from dataclasses import asdict

from sqlmodel.ext.asyncio.session import AsyncSession

from python_coach.clients.sandbox_result import TestRunResult
from python_coach.storage.models.submission import Submission, SubmissionStatus


class SubmissionsMixin:
    """Persist and fetch graded submissions."""

    session: AsyncSession

    async def create_pending_submission(self, exercise_id: int, code: str) -> Submission:
        """Insert a submission in PENDING state and return it with its id."""
        submission = Submission(exercise_id=exercise_id, code=code)
        self.session.add(submission)
        await self.session.flush()
        await self.session.refresh(submission)
        return submission

    async def finalize_submission(
        self,
        submission: Submission,
        status: SubmissionStatus,
        result: TestRunResult,
    ) -> Submission:
        """Attach the structured verdict to a submission and persist it."""
        submission.status = status
        submission.result = asdict(result)
        self.session.add(submission)
        await self.session.flush()
        await self.session.refresh(submission)
        return submission

    async def get_submission(self, submission_id: int) -> Submission | None:
        """Fetch one submission by id."""
        return await self.session.get(Submission, submission_id)
