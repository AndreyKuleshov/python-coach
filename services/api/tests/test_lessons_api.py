"""API tests for the lesson read endpoint (GET /api/lessons/{slug}).

Drives the real app + DB via ASGITransport. The load-bearing assertion here is
that test sources — visible *and* hidden — never leak to the frontend: the
`ExerciseDTO` deliberately omits them (anti-cheat).
"""

import httpx
import pytest

from conftest import SeededExercise

pytestmark = [pytest.mark.db]


@pytest.mark.smoke
async def test_get_existing_lesson_returns_exercises(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """A seeded, published lesson is returned with its ordered exercises."""
    res = await client.get(f"/api/lessons/{seed_exercise.lesson_slug}")

    assert res.status_code == 200
    body = res.json()
    assert body["slug"] == seed_exercise.lesson_slug
    assert body["is_published"] is True
    assert len(body["exercises"]) == 1
    ex = body["exercises"][0]
    assert ex["id"] == seed_exercise.exercise_id
    assert ex["slug"] == seed_exercise.exercise_slug
    assert ex["starter_code"] == "def answer():\n    return 0\n"


async def test_get_missing_lesson_is_404(client: httpx.AsyncClient) -> None:
    """An unknown slug yields a 404, not an empty 200."""
    res = await client.get("/api/lessons/this-slug-does-not-exist-zzz")
    assert res.status_code == 404


@pytest.mark.regression
async def test_lesson_response_never_leaks_test_sources(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """Neither visible nor hidden pytest sources appear anywhere in the payload.

    This is the anti-cheat contract: the route shapes exercises without a
    `tests` field. We assert structurally (no key) AND on the raw bytes (the
    test filenames / `from solution import` must not appear at all).
    """
    res = await client.get(f"/api/lessons/{seed_exercise.lesson_slug}")
    assert res.status_code == 200

    ex = res.json()["exercises"][0]
    assert "tests" not in ex
    assert "exercise_test" not in ex

    raw = res.text
    assert seed_exercise.visible_test_filename not in raw
    assert seed_exercise.hidden_test_filename not in raw
    assert "from solution import" not in raw
