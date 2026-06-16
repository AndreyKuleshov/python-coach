"""Profile/progress aggregate endpoint and its DTOs.

Authenticated-only: returns the current user's email plus their progress across
all published lessons. Scoped to the bearer-token user — no other user's data
is reachable here.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from python_coach.controllers.profile import get_profile
from python_coach.transport.deps import CurrentUserDep, StorageDep

router = APIRouter(prefix="/api/profile", tags=["profile"])


class LocalizedText(BaseModel):
    """A prose field in every supported locale (fallback already applied)."""

    en: str
    ru: str


class ProfileLessonDTO(BaseModel):
    """One published lesson with the user's solved/total counts and gating state."""

    slug: str
    title: LocalizedText
    position: int
    total_exercises: int
    solved_exercises: int
    is_completed: bool
    is_unlocked: bool


class ProfileDTO(BaseModel):
    """Personal cabinet: identity + per-lesson progress + completion totals."""

    email: str
    lessons: list[ProfileLessonDTO]
    lessons_completed: int
    lessons_total: int


@router.get("", response_model=ProfileDTO)
async def read_profile(user: CurrentUserDep, storage: StorageDep) -> ProfileDTO:
    """Return the current user's progress aggregate across all published lessons."""
    profile = await get_profile(user.id or 0, user.email, storage)
    return ProfileDTO(
        email=profile.email,
        lessons=[
            ProfileLessonDTO(
                slug=lesson.slug,
                title=LocalizedText(**lesson.title),
                position=lesson.position,
                total_exercises=lesson.total_exercises,
                solved_exercises=lesson.solved_exercises,
                is_completed=lesson.is_completed,
                is_unlocked=lesson.is_unlocked,
            )
            for lesson in profile.lessons
        ],
        lessons_completed=profile.lessons_completed,
        lessons_total=profile.lessons_total,
    )
