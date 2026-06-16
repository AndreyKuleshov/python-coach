"""Per-exercise progress read/update access for Storage."""

from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from python_coach.storage.models.submission import Progress


class ProgressMixin:
    """Maintain the per-exercise progress roll-up."""

    session: AsyncSession

    async def get_progress(self, user_id: int, exercise_id: int) -> Progress | None:
        """Fetch the progress row for a (user, exercise), if any attempt was made."""
        stmt = select(Progress).where(
            Progress.user_id == user_id, Progress.exercise_id == exercise_id
        )
        result = await self.session.exec(stmt)
        return result.first()

    async def record_attempt(
        self, user_id: int, exercise_id: int, submission_id: int, solved: bool
    ) -> Progress:
        """Upsert progress after a graded attempt: bump counters, mark solved once."""
        progress = await self.get_progress(user_id, exercise_id)
        if progress is None:
            progress = Progress(user_id=user_id, exercise_id=exercise_id)

        progress.attempts += 1
        progress.last_submission_id = submission_id
        progress.updated_at = datetime.now(UTC)
        # First successful solve sticks; later failures don't un-solve it.
        if solved and not progress.is_solved:
            progress.is_solved = True
            progress.solved_at = datetime.now(UTC)

        self.session.add(progress)
        await self.session.flush()
        await self.session.refresh(progress)
        return progress
