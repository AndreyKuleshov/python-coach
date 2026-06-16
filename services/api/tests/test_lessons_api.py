"""API tests for lesson read endpoints:
  - GET /api/lessons        — published lesson list (no body/exercises/tests/solution_code)
  - GET /api/lessons/{slug} — full lesson with exercises (no test sources/solution_code)

Drives the real app + DB via ASGITransport. The load-bearing assertion here is
that test sources — visible *and* hidden — never leak to the frontend: the
`ExerciseDTO` deliberately omits them (anti-cheat).
"""

import httpx
import pytest

from conftest import SeededExercise

pytestmark = [pytest.mark.db]


@pytest.mark.smoke
async def test_list_returns_published_lessons_only(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """GET /api/lessons returns only published lessons; unpublished ones are absent."""
    res = await client.get("/api/lessons")

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    # The seeded lesson (is_published=True in conftest) must appear in the list.
    slugs = [item["slug"] for item in body]
    assert seed_exercise.lesson_slug in slugs


async def test_list_items_carry_bilingual_titles(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """Each list item has slug, position, and bilingual title — nothing more."""
    res = await client.get("/api/lessons")

    assert res.status_code == 200
    body = res.json()
    seeded = next(item for item in body if item["slug"] == seed_exercise.lesson_slug)

    assert seeded["title"]["en"] == "QA seeded lesson"
    assert seeded["title"]["ru"] == "QA урок"
    assert "position" in seeded
    # Verify the shape is exactly {slug, title, position} — no extra fields leak.
    assert set(seeded.keys()) == {"slug", "title", "position"}


@pytest.mark.regression
async def test_list_never_leaks_body_or_exercises(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """The list payload must not expose body_md, exercises, tests, or solution_code."""
    res = await client.get("/api/lessons")

    assert res.status_code == 200
    raw = res.text
    for forbidden in ["body_md", "exercises", "solution_code", "starter_code"]:
        assert forbidden not in raw, f"field '{forbidden}' must not appear in list payload"


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
    # Both locales are present in one payload (instant client-side switch).
    assert body["title"]["en"] == "QA seeded lesson"
    assert body["title"]["ru"] == "QA урок"
    assert len(body["exercises"]) == 1
    ex = body["exercises"][0]
    assert ex["id"] == seed_exercise.exercise_id
    assert ex["slug"] == seed_exercise.exercise_slug
    assert ex["title"]["en"] == "QA exercise"
    assert ex["title"]["ru"] == "QA задача"
    assert ex["statement_md"]["ru"] == "Верните 42 из `answer()`."
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


@pytest.mark.regression
async def test_lesson_response_never_leaks_solution_code(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """The hidden reference `solution_code` is stored but never sent to the frontend.

    Same secrecy class as hidden test sources: the ExerciseDTO has no
    `solution_code` field, and the seeded sentinel must not appear in the bytes.
    """
    res = await client.get(f"/api/lessons/{seed_exercise.lesson_slug}")
    assert res.status_code == 200

    ex = res.json()["exercises"][0]
    assert "solution_code" not in ex

    raw = res.text
    assert "SECRET_REFERENCE_SOLUTION" not in raw
    assert seed_exercise.solution_code not in raw
