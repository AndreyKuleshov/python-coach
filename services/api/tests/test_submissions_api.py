"""API tests for the submit -> sandbox -> grade -> result flow.

These run the REAL Docker sandbox (no mocking): a correct solution must grade
as passed, a wrong one must surface the real pytest assertion message, and the
graded submission must be retrievable by id afterwards.
"""

import httpx
import pytest

from conftest import SeededExercise

pytestmark = [pytest.mark.db, pytest.mark.sandbox]

_CORRECT = "def answer():\n    return 42\n"
_WRONG = "def answer():\n    return 7\n"


@pytest.mark.smoke
async def test_correct_solution_passes(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """Correct code grades to status=passed with every test green."""
    res = await client.post(
        "/api/submissions",
        json={"exercise_id": seed_exercise.exercise_id, "code": _CORRECT},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "passed"
    assert body["passed"] is True
    # Both the visible and the hidden test run; the source of neither leaked.
    assert body["total"] == 2
    assert body["passed_count"] == 2
    assert body["failed_count"] == 0
    assert all(t["outcome"] == "passed" for t in body["tests"])
    assert body["runner_error"] == ""


@pytest.mark.regression
async def test_wrong_solution_fails_with_real_assertion(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """Wrong code grades to status=failed and surfaces the verbatim assertion."""
    res = await client.post(
        "/api/submissions",
        json={"exercise_id": seed_exercise.exercise_id, "code": _WRONG},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failed"
    assert body["passed"] is False
    assert body["failed_count"] >= 1
    assert body["runner_error"] == ""

    # The custom assertion message from the seeded test must reach the panel.
    failed = [t for t in body["tests"] if t["outcome"] == "failed"]
    assert failed, "expected at least one failed test in the result"
    assert any("answer() must return 42" in t["message"] for t in failed)


async def test_submit_to_unknown_exercise_is_404(client: httpx.AsyncClient) -> None:
    """Submitting against a non-existent exercise id is a clean 404."""
    res = await client.post(
        "/api/submissions", json={"exercise_id": 2_000_000_000, "code": _CORRECT}
    )
    assert res.status_code == 404


async def test_graded_submission_is_retrievable(
    client: httpx.AsyncClient, seed_exercise: SeededExercise
) -> None:
    """A submission can be fetched by id and matches the grading response."""
    created = await client.post(
        "/api/submissions",
        json={"exercise_id": seed_exercise.exercise_id, "code": _CORRECT},
    )
    assert created.status_code == 200
    submission_id = created.json()["id"]

    fetched = await client.get(f"/api/submissions/{submission_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["id"] == submission_id
    assert body["exercise_id"] == seed_exercise.exercise_id
    assert body["status"] == "passed"


async def test_get_missing_submission_is_404(client: httpx.AsyncClient) -> None:
    """An unknown submission id is a 404."""
    res = await client.get("/api/submissions/2000000000")
    assert res.status_code == 404
