"""Lesson ingest CLI — load a lesson JSON file into the database (upsert by slug).

This is the canonical ingest path documented in STORAGE_CONTRACT.md: the
methodist authors a JSON file matching the contract and runs:

    uv run python -m python_coach.seed fixtures/placeholder_lesson.json

Bilingual prose fields (`title`, `body_md`, exercise `title`/`statement_md`)
are objects keyed by locale: ``{"en": "...", "ru": "..."}``. For backward
compatibility a bare string is accepted and treated as a single-locale value
(it lands under every locale via fallback) so a legacy single-locale fixture
still ingests without crashing. Real content MUST provide both locales.

It is a one-off CLI script, so console output (print) is intentional and
allowed per .claude/rules/all-languages.md.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlmodel import delete, select

from python_coach.storage.db import session_factory
from python_coach.storage.models.lesson import (
    SUPPORTED_LOCALES,
    Exercise,
    ExerciseTest,
    ExerciseTranslation,
    Lesson,
    LessonTranslation,
)


def _locales(value: Any) -> dict[str, str]:
    """Normalise a prose field into a {locale: text} dict with fallback.

    Accepts a ``{"en": ..., "ru": ...}`` object (canonical) or a bare string
    (legacy single-locale). A missing locale borrows a present one — English
    first — so no locale ends up empty when at least one was provided.
    """
    if isinstance(value, str):
        raw = {"en": value}
    elif isinstance(value, dict):
        raw = {str(k): str(v) for k, v in value.items() if v}
    else:
        raw = {}
    present = {loc: text for loc, text in raw.items() if text}
    if not present:
        return {loc: "" for loc in SUPPORTED_LOCALES}
    fallback = present.get("en") or next(iter(present.values()))
    return {loc: present.get(loc, fallback) for loc in SUPPORTED_LOCALES}


def _solution_code(ex: dict[str, Any]) -> str | None:
    """Read the hidden reference solution (canonical `solution_code`, legacy `_solution_code`)."""
    value = ex.get("solution_code", ex.get("_solution_code"))
    if value is None:
        return None
    return str(value)


async def _ingest(data: dict[str, Any]) -> None:
    """Upsert one lesson (and its exercises + tests + translations) from a contract document."""
    factory = session_factory()
    async with factory() as session:
        # Upsert by slug: delete an existing lesson (cascades to all children).
        existing = (await session.exec(select(Lesson).where(Lesson.slug == data["slug"]))).first()
        if existing is not None:
            await session.exec(delete(Lesson).where(Lesson.id == existing.id))  # type: ignore[arg-type, call-overload]
            await session.flush()

        lesson = Lesson(
            slug=data["slug"],
            position=data.get("position", 0),
            is_published=data.get("is_published", False),
        )
        session.add(lesson)
        await session.flush()

        title = _locales(data["title"])
        body = _locales(data["body_md"])
        for locale in SUPPORTED_LOCALES:
            session.add(
                LessonTranslation(
                    lesson_id=lesson.id or 0,
                    locale=locale,
                    title=title[locale],
                    body_md=body[locale],
                )
            )

        for ex in data.get("exercises", []):
            exercise = Exercise(
                lesson_id=lesson.id or 0,
                slug=ex["slug"],
                starter_code=ex.get("starter_code", ""),
                solution_code=_solution_code(ex),
                solution_module=ex.get("solution_module", "solution"),
                position=ex.get("position", 0),
            )
            session.add(exercise)
            await session.flush()

            ex_title = _locales(ex["title"])
            ex_statement = _locales(ex["statement_md"])
            for locale in SUPPORTED_LOCALES:
                session.add(
                    ExerciseTranslation(
                        exercise_id=exercise.id or 0,
                        locale=locale,
                        title=ex_title[locale],
                        statement_md=ex_statement[locale],
                    )
                )

            for test in ex.get("tests", []):
                session.add(
                    ExerciseTest(
                        exercise_id=exercise.id or 0,
                        filename=test["filename"],
                        content=test.get("content", ""),
                        is_hidden=test.get("is_hidden", False),
                        position=test.get("position", 0),
                    )
                )

        await session.commit()
        print(f"ingested lesson '{lesson.slug}' with {len(data.get('exercises', []))} exercise(s)")


def main() -> int:
    """Entry point: ingest the lesson JSON path given as argv[1]."""
    if len(sys.argv) != 2:
        print("usage: python -m python_coach.seed <lesson.json>", file=sys.stderr)
        return 2
    # Read the file synchronously here (CLI startup), not inside the async ingest.
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    asyncio.run(_ingest(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
