"""The single Storage repository surface, composed from per-domain mixins.

Per .claude/rules/api-layers.md: one Storage class owns the session; no
per-aggregate Repository classes, no Protocol/ABC while there is one impl.
"""

from sqlmodel.ext.asyncio.session import AsyncSession

from python_coach.storage._lessons import LessonsMixin
from python_coach.storage._progress import ProgressMixin
from python_coach.storage._submissions import SubmissionsMixin
from python_coach.storage._users import UsersMixin


class Storage(LessonsMixin, SubmissionsMixin, ProgressMixin, UsersMixin):
    """Repository facade owning one AsyncSession for the request lifetime."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
