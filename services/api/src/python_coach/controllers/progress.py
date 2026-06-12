"""Progress read use-case."""

from python_coach.storage.models.submission import Progress
from python_coach.storage.storage import Storage


async def get_progress(exercise_id: int, storage: Storage) -> Progress | None:
    """Return the per-exercise progress roll-up, or None if never attempted."""
    return await storage.get_progress(exercise_id)
