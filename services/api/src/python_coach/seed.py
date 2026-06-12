"""Lesson ingest CLI — load a lesson JSON file into the database (upsert by slug).

This is the canonical ingest path documented in STORAGE_CONTRACT.md: the
methodist authors a JSON file matching the contract and runs:

    uv run python -m python_coach.seed fixtures/placeholder_lesson.json

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
from python_coach.storage.models.lesson import Exercise, ExerciseTest, Lesson


async def _ingest(data: dict[str, Any]) -> None:
    """Upsert one lesson (and its exercises + tests) from a parsed contract document."""
    factory = session_factory()
    async with factory() as session:
        # Upsert by slug: delete an existing lesson (cascades to exercises/tests).
        existing = (await session.exec(select(Lesson).where(Lesson.slug == data["slug"]))).first()
        if existing is not None:
            await session.exec(delete(Lesson).where(Lesson.id == existing.id))  # type: ignore[arg-type, call-overload]
            await session.flush()

        lesson = Lesson(
            slug=data["slug"],
            title=data["title"],
            body_md=data["body_md"],
            position=data.get("position", 0),
            is_published=data.get("is_published", False),
        )
        session.add(lesson)
        await session.flush()

        for ex in data.get("exercises", []):
            exercise = Exercise(
                lesson_id=lesson.id or 0,
                slug=ex["slug"],
                title=ex["title"],
                statement_md=ex["statement_md"],
                starter_code=ex.get("starter_code", ""),
                solution_module=ex.get("solution_module", "solution"),
                position=ex.get("position", 0),
            )
            session.add(exercise)
            await session.flush()

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
