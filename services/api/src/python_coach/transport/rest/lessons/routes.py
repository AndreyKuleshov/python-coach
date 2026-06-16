"""Lesson read endpoints + their response DTOs.

The payload carries BOTH locales for every prose field so the frontend can
switch language with no re-fetch. It deliberately omits test sources (visible
and hidden) and `solution_code` — anti-cheat: those never reach the browser.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from python_coach.controllers.lessons import get_lesson, list_published_lessons
from python_coach.transport.deps import StorageDep

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
    """Minimal lesson metadata for the curriculum list — no body, exercises, or tests."""

    slug: str
    title: LocalizedText
    position: int


class LessonDTO(BaseModel):
    """A lesson plus its ordered exercises, both locales in one payload."""

    id: int
    slug: str
    title: LocalizedText
    body_md: LocalizedText
    is_published: bool
    exercises: list[ExerciseDTO]


@router.get("", response_model=list[LessonSummaryDTO])
async def read_lesson_list(storage: StorageDep) -> list[LessonSummaryDTO]:
    """Return published lessons ordered by position — list metadata only."""
    summaries = await list_published_lessons(storage)
    return [
        LessonSummaryDTO(
            slug=s.slug,
            title=LocalizedText(**s.title),
            position=s.position,
        )
        for s in summaries
    ]


@router.get("/{slug}", response_model=LessonDTO)
async def read_lesson(slug: str, storage: StorageDep) -> LessonDTO:
    """Return a lesson with its exercises (both locales) for rendering."""
    view = await get_lesson(slug, storage)
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
    )
