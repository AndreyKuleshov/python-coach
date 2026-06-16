"""Lesson read endpoints + their response DTOs.

Both endpoints REQUIRE a valid bearer token (CurrentUserDep): no lesson content
is reachable without logging in. The payload carries BOTH locales for every
prose field so the frontend can switch language with no re-fetch. It
deliberately omits test sources (visible and hidden) and `solution_code` —
anti-cheat: those never reach the browser.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from python_coach.controllers.lessons import (
    LessonLockedError,
    get_lesson,
    list_published_lessons,
)
from python_coach.transport.deps import CurrentUserDep, StorageDep

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


class LocalizedText(BaseModel):
    """A prose field in every supported locale (fallback already applied)."""

    en: str
    ru: str


class ExerciseDTO(BaseModel):
    """An exercise as shown on the lesson page (no test sources, no solution)."""

    id: int
    slug: str
    title: LocalizedText
    statement_md: LocalizedText
    starter_code: str


class LessonSummaryDTO(BaseModel):
    """Minimal lesson metadata for the curriculum list — no body, exercises, or tests.

    Carries the per-user `is_completed` / `is_unlocked` flags so the list can
    show a completed badge and gate locked rows.
    """

    slug: str
    title: LocalizedText
    position: int
    is_completed: bool
    is_unlocked: bool


class LessonDTO(BaseModel):
    """A lesson plus its ordered exercises, both locales in one payload.

    `is_completed` (all exercises solved by the user) and `next_slug` (the next
    published lesson by position, or null when last) drive the completed state
    and the "Next lesson" button on the lesson view.
    """

    id: int
    slug: str
    title: LocalizedText
    body_md: LocalizedText
    is_published: bool
    exercises: list[ExerciseDTO]
    is_completed: bool
    next_slug: str | None


@router.get("", response_model=list[LessonSummaryDTO])
async def read_lesson_list(user: CurrentUserDep, storage: StorageDep) -> list[LessonSummaryDTO]:
    """Return published lessons (ordered) with per-user completion + unlock state.

    Authenticated-only: no lesson content (not even titles) is reachable without
    a valid bearer token. Completion/unlock are derived for the current user.
    """
    summaries = await list_published_lessons(user.id or 0, storage)
    return [
        LessonSummaryDTO(
            slug=s.slug,
            title=LocalizedText(**s.title),
            position=s.position,
            is_completed=s.is_completed,
            is_unlocked=s.is_unlocked,
        )
        for s in summaries
    ]


@router.get("/{slug}", response_model=LessonDTO)
async def read_lesson(slug: str, user: CurrentUserDep, storage: StorageDep) -> LessonDTO:
    """Return a lesson with its exercises (both locales) for rendering.

    Authenticated-only. A lesson the user has not unlocked is NOT served: the
    locked case raises LessonLockedError -> 403 (no content leaks). This is the
    real server-side gate, mirrored — not replaced — by the frontend redirect.
    """
    try:
        view = await get_lesson(slug, user.id or 0, storage)
    except LessonLockedError as exc:
        raise HTTPException(status_code=403, detail="lesson is locked") from exc
    if view is None:
        raise HTTPException(status_code=404, detail="lesson not found")

    return LessonDTO(
        id=view.id,
        slug=view.slug,
        title=LocalizedText(**view.title),
        body_md=LocalizedText(**view.body_md),
        is_published=view.is_published,
        exercises=[
            ExerciseDTO(
                id=ex.id,
                slug=ex.slug,
                title=LocalizedText(**ex.title),
                statement_md=LocalizedText(**ex.statement_md),
                starter_code=ex.starter_code,
            )
            for ex in view.exercises
        ],
        is_completed=view.is_completed,
        next_slug=view.next_slug,
    )
