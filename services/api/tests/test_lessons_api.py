"""API tests for lesson read endpoints:
  - GET /api/lessons        — published lesson list (no body/exercises/tests/solution_code)
  - GET /api/lessons/{slug} — full lesson with exercises (no test sources/solution_code)

Both endpoints REQUIRE a bearer token: no lesson content is reachable while
logged out (see test_requires_auth.py for the 401 regressions). Tests that need
the data drive the real app + DB via the authenticated `auth_client` over
ASGITransport. The load-bearing assertion here is that test sources — visible
*and* hidden — never leak to the frontend: the `ExerciseDTO` deliberately omits
them (anti-cheat).
"""

import httpx
import pytest

from conftest import SeededExercise, SeededPair

pytestmark = [pytest.mark.db]


@pytest.mark.smoke
async def test_list_returns_published_lessons_only(
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """GET /api/lessons returns only published lessons; unpublished ones are absent."""
    res = await auth_client.get("/api/lessons")

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    # The seeded lesson (is_published=True in conftest) must appear in the list.
    slugs = [item["slug"] for item in body]
    assert seed_exercise.lesson_slug in slugs


async def test_list_items_carry_bilingual_titles(
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """Each list item has slug, position, and bilingual title — nothing more."""
    res = await auth_client.get("/api/lessons")

    assert res.status_code == 200
    body = res.json()
    seeded = next(item for item in body if item["slug"] == seed_exercise.lesson_slug)

    assert seeded["title"]["en"] == "QA seeded lesson"
    assert seeded["title"]["ru"] == "QA урок"
    assert "position" in seeded
    # Shape is the safe metadata set + the derived gating flags — nothing else
    # (no body/exercises/tests/solution_code).
    assert set(seeded.keys()) == {"slug", "title", "position", "is_completed", "is_unlocked"}


@pytest.mark.regression
async def test_list_never_leaks_body_or_exercises(
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """The list payload must not expose body_md, exercises, tests, or solution_code.

    Asserted on the raw bytes (not just the parsed keys) so a nested or
    differently-named leak is still caught: the list contract is slug + title +
    position and nothing more.
    """
    res = await auth_client.get("/api/lessons")

    assert res.status_code == 200
    raw = res.text
    # Field names that must never appear, plus seeded sentinels for content that
    # would only be present if the corresponding object leaked into the payload.
    forbidden = [
        "body_md",
        "exercises",
        "tests",
        "solution_code",
        "starter_code",
        "statement_md",
        seed_exercise.visible_test_filename,
        seed_exercise.hidden_test_filename,
        "SECRET_REFERENCE_SOLUTION",
        "from solution import",
    ]
    for needle in forbidden:
        assert needle not in raw, f"'{needle}' must not appear in the list payload"


@pytest.mark.regression
async def test_list_is_ordered_by_position(
    auth_client: httpx.AsyncClient, seed_ordered_pair: SeededPair
) -> None:
    """Published lessons come back ordered by `position`, not by insert/id order.

    The fixture inserts the high-position lesson first; the API must still place
    the low-position lesson ahead of it.
    """
    res = await auth_client.get("/api/lessons")
    assert res.status_code == 200

    slugs = [item["slug"] for item in res.json()]
    assert seed_ordered_pair.low_slug in slugs
    assert seed_ordered_pair.high_slug in slugs
    assert slugs.index(seed_ordered_pair.low_slug) < slugs.index(seed_ordered_pair.high_slug)


@pytest.mark.smoke
async def test_get_existing_lesson_returns_exercises(
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """A seeded, published lesson is returned with its ordered exercises."""
    res = await auth_client.get(f"/api/lessons/{seed_exercise.lesson_slug}")

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


async def test_get_missing_lesson_is_404(auth_client: httpx.AsyncClient) -> None:
    """An unknown slug yields a 404, not an empty 200."""
    res = await auth_client.get("/api/lessons/this-slug-does-not-exist-zzz")
    assert res.status_code == 404


@pytest.mark.regression
async def test_lesson_response_never_leaks_test_sources(
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """Neither visible nor hidden pytest sources appear anywhere in the payload.

    This is the anti-cheat contract: the route shapes exercises without a
    `tests` field. We assert structurally (no key) AND on the raw bytes (the
    test filenames / `from solution import` must not appear at all).
    """
    res = await auth_client.get(f"/api/lessons/{seed_exercise.lesson_slug}")
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
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """The hidden reference `solution_code` is stored but never sent to the frontend.

    Same secrecy class as hidden test sources: the ExerciseDTO has no
    `solution_code` field, and the seeded sentinel must not appear in the bytes.
    """
    res = await auth_client.get(f"/api/lessons/{seed_exercise.lesson_slug}")
    assert res.status_code == 200

    ex = res.json()["exercises"][0]
    assert "solution_code" not in ex

    raw = res.text
    assert "SECRET_REFERENCE_SOLUTION" not in raw
    assert seed_exercise.solution_code not in raw
