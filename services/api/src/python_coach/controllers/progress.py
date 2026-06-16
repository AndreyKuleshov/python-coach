"""Progress read use-case."""

from python_coach.storage.models.submission import Progress
from python_coach.storage.storage import Storage


async def get_progress(user_id: int, exercise_id: int, storage: Storage) -> Progress | None:
    """Return the per-(user, exercise) progress roll-up, or None if never attempted."""
    return await storage.get_progress(user_id, exercise_id)
