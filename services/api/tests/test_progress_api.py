"""API tests for per-exercise progress (GET /api/progress/{exercise_id}).

Progress is written as a side-effect of grading, so these tests drive real
submissions through the sandbox and then assert the roll-up: attempts increment
on a real wrong answer, and `is_solved` is sticky once a correct answer lands.
"""

import httpx
import pytest

from conftest import SeededExercise

pytestmark = [pytest.mark.db, pytest.mark.sandbox]

_CORRECT = "def answer():\n    return 42\n"
_WRONG = "def answer():\n    return 7\n"


async def _submit(client: httpx.AsyncClient, exercise_id: int, code: str) -> None:
    """Submit `code` for `exercise_id`, asserting the grade call itself succeeded."""
    res = await client.post("/api/submissions", json={"exercise_id": exercise_id, "code": code})
    assert res.status_code == 200


async def test_progress_without_token_is_401(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """Reading progress without a token is rejected with 401 (protected endpoint)."""
    res = await client.get(f"/api/progress/{seed_exercise.exercise_id}")
    assert res.status_code == 401


async def test_progress_zero_before_any_attempt(
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """A never-attempted exercise reports zeros, not a 404."""
    res = await auth_client.get(f"/api/progress/{seed_exercise.exercise_id}")

    assert res.status_code == 200
    body = res.json()
    assert body["exercise_id"] == seed_exercise.exercise_id
    assert body["is_solved"] is False
    assert body["attempts"] == 0
    assert body["last_submission_id"] is None
    assert body["solved_at"] is None


@pytest.mark.regression
async def test_attempts_increment_on_wrong_answer(
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """Each real (non-infra) failed grade bumps the attempt counter."""
    await _submit(auth_client, seed_exercise.exercise_id, _WRONG)
    await _submit(auth_client, seed_exercise.exercise_id, _WRONG)

    res = await auth_client.get(f"/api/progress/{seed_exercise.exercise_id}")
    body = res.json()
    assert body["attempts"] == 2
    assert body["is_solved"] is False
    assert body["solved_at"] is None


@pytest.mark.regression
async def test_solved_is_sticky_after_later_failure(
    auth_client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """Once solved, a subsequent wrong answer must not un-solve the exercise."""
    await _submit(auth_client, seed_exercise.exercise_id, _CORRECT)

    solved = (await auth_client.get(f"/api/progress/{seed_exercise.exercise_id}")).json()
    assert solved["is_solved"] is True
    assert solved["attempts"] == 1
    assert solved["solved_at"] is not None
    solved_at = solved["solved_at"]

    # A later failure bumps attempts but must leave is_solved / solved_at intact.
    await _submit(auth_client, seed_exercise.exercise_id, _WRONG)

    after = (await auth_client.get(f"/api/progress/{seed_exercise.exercise_id}")).json()
    assert after["is_solved"] is True, "solve must stick across a later failure"
    assert after["attempts"] == 2
    assert after["solved_at"] == solved_at, "solved_at must not move on re-failure"


@pytest.mark.regression
async def test_user_cannot_see_another_users_progress(
    auth_client: httpx.AsyncClient,
    second_auth_client: httpx.AsyncClient,
    seed_exercise: SeededExercise,
) -> None:
    """User A must see zero progress even after user B submits a correct solution.

    Progress rows are scoped per user_id. When user A has never attempted an
    exercise, GET /api/progress/{id} must return zeros regardless of what user B
    has done — the storage layer must not leak cross-user rows.
    """
    # User B solves the exercise; their progress row is now non-zero.
    await _submit(second_auth_client, seed_exercise.exercise_id, _CORRECT)
    b_progress = (await second_auth_client.get(f"/api/progress/{seed_exercise.exercise_id}")).json()
    assert b_progress["is_solved"] is True, "user B must be solved after a correct submit"

    # User A (who never submitted) must still see zeros — not user B's data.
    a_progress = (await auth_client.get(f"/api/progress/{seed_exercise.exercise_id}")).json()
    assert a_progress["is_solved"] is False, (
        "user A must not see user B's solved state (IDOR guard)"
    )
    assert a_progress["attempts"] == 0, "user A must not see user B's attempt count (IDOR guard)"
