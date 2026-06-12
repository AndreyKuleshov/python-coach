"""Unit tests for grading verdict mapping (no DB / no Docker needed)."""

from python_coach.clients.sandbox_result import TestOutcome, TestResult, TestRunResult
from python_coach.controllers.submissions import _status_from_result
from python_coach.storage.models.submission import SubmissionStatus


def _result(*, passed: bool, runner_error: str = "") -> TestRunResult:
    """Build a minimal TestRunResult for status-mapping assertions."""
    tests = [TestResult(name="t", outcome=TestOutcome.PASSED, duration_seconds=0.0)]
    return TestRunResult(
        passed=passed,
        total=1,
        passed_count=1 if passed else 0,
        failed_count=0 if passed else 1,
        tests=tests,
        runner_error=runner_error,
    )


def test_passed_result_maps_to_passed() -> None:
    assert _status_from_result(_result(passed=True)) == SubmissionStatus.PASSED


def test_failed_result_maps_to_failed() -> None:
    assert _status_from_result(_result(passed=False)) == SubmissionStatus.FAILED


def test_wall_clock_error_maps_to_timeout() -> None:
    res = _result(passed=False, runner_error="execution exceeded 10s wall-clock limit")
    assert _status_from_result(res) == SubmissionStatus.TIMEOUT


def test_other_runner_error_maps_to_error() -> None:
    res = _result(passed=False, runner_error="runner emitted invalid JSON")
    assert _status_from_result(res) == SubmissionStatus.ERROR
