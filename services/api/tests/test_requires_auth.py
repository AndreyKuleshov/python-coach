"""Regression: lesson content endpoints reject unauthenticated requests.

The access model is "no content without a token". These tests pin the 401 for
both lesson endpoints when no/invalid bearer is sent, and confirm the SAME
endpoints return 200 once a valid token is attached — so the gate is real, not
a side effect of a missing seed.
"""

import httpx
import pytest

from conftest import SeededExercise

pytestmark = [pytest.mark.db]


@pytest.mark.regression
async def test_lesson_list_requires_token(client: httpx.AsyncClient) -> None:
    """GET /api/lessons without a bearer token is 401 (no content leaks)."""
    res = await client.get("/api/lessons")
    assert res.status_code == 401


@pytest.mark.regression
async def test_lesson_detail_requires_token(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """GET /api/lessons/{slug} without a token is 401 even for a real lesson.

    Seeding a real, published lesson rules out a 404-masquerading-as-protected
    false positive: the lesson exists, yet a tokenless request still gets 401.
    """
    res = await client.get(f"/api/lessons/{seed_exercise.lesson_slug}")
    assert res.status_code == 401


@pytest.mark.regression
async def test_lesson_endpoints_reject_garbage_token(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """An invalid/garbage bearer token is rejected with 401 on both endpoints."""
    headers = {"Authorization": "Bearer not-a-real-jwt"}
    list_res = await client.get("/api/lessons", headers=headers)
    detail_res = await client.get(f"/api/lessons/{seed_exercise.lesson_slug}", headers=headers)
    assert list_res.status_code == 401
    assert detail_res.status_code == 401


@pytest.mark.smoke
async def test_lesson_endpoints_open_with_valid_token(
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """With a valid token, both lesson endpoints return 200 — the gate opens."""
    list_res = await auth_client.get("/api/lessons")
    detail_res = await auth_client.get(f"/api/lessons/{seed_exercise.lesson_slug}")
    assert list_res.status_code == 200
    assert detail_res.status_code == 200
