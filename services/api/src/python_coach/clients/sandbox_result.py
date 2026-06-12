"""Structured result types returned by the sandbox runner.

These dataclasses are the contract between the sandbox client and the rest of
the app. The sandbox container emits a JSON document with this exact shape on
stdout; the client parses it back into these dataclasses.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class TestOutcome(StrEnum):
    """Per-test outcome as reported by pytest."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class TestResult:
    """One pytest test node's outcome and (on failure) its message."""

    name: str
    outcome: TestOutcome
    duration_seconds: float
    message: str = ""


@dataclass(frozen=True, slots=True)
class TestRunResult:
    """Aggregate verdict of running an exercise's tests against user code."""

    # True only when every test passed and the runner itself did not error.
    passed: bool
    total: int
    passed_count: int
    failed_count: int
    tests: list[TestResult] = field(default_factory=list)
    # Captured stdout/stderr from the run, truncated by the runner.
    stdout: str = ""
    stderr: str = ""
    # Set when the run failed for non-test reasons (timeout, crash, OOM).
    runner_error: str = ""
