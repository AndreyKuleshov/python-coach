"""Lesson read endpoints + their response DTOs."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from python_coach.controllers.lessons import get_lesson
from python_coach.transport.deps import StorageDep

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


class ExerciseDTO(BaseModel):
    """An exercise as shown on the lesson page (no test sources leaked)."""

    id: int
    slug: str
    title: str
    statement_md: str
    starter_code: str


class LessonDTO(BaseModel):
    """A lesson plus its ordered exercises."""

    id: int
    slug: str
    title: str
    body_md: str
    is_published: bool
    exercises: list[ExerciseDTO]


@router.get("/{slug}", response_model=LessonDTO)
async def read_lesson(slug: str, storage: StorageDep) -> LessonDTO:
    """Return a lesson with its exercises for rendering."""
    view = await get_lesson(slug, storage)
    if view is None:
        raise HTTPException(status_code=404, detail="lesson not found")

    return LessonDTO(
        id=view.lesson.id or 0,
        slug=view.lesson.slug,
        title=view.lesson.title,
        body_md=view.lesson.body_md,
        is_published=view.lesson.is_published,
        exercises=[
            ExerciseDTO(
                id=ex.id or 0,
                slug=ex.slug,
                title=ex.title,
                statement_md=ex.statement_md,
                starter_code=ex.starter_code,
            )
            for ex in view.exercises
        ],
    )
