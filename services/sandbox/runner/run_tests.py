"""In-container grader: copy user files to a tmpfs workdir, run pytest, emit JSON.

This runs INSIDE the sandbox container as an unprivileged user. It must not
trust /code (user-supplied). It collects per-test outcomes via a tiny pytest
plugin and prints a single JSON document between markers on stdout for the
host SandboxClient to parse.

Console output here is intentional: this is a CLI entrypoint, not a service
(see .claude/rules/all-languages.md), and stdout IS the transport.
"""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

_RESULT_BEGIN = "<<<PYTHON_COACH_RESULT_BEGIN>>>"
_RESULT_END = "<<<PYTHON_COACH_RESULT_END>>>"

_CODE_DIR = Path("/code")  # read-only mount of user files
_WORK_DIR = Path("/work")  # tmpfs, writable, noexec


class _Collector:
    """pytest plugin capturing each test's outcome and failure message."""

    def __init__(self) -> None:
        self.tests: list[dict[str, object]] = []

    def pytest_runtest_logreport(self, report: "pytest.TestReport") -> None:
        """Record the call-phase report (plus setup/teardown errors) per test."""
        # 'call' is the test body; setup/teardown only matter when they error.
        if report.when == "call" or (report.when in {"setup", "teardown"} and report.failed):
            if report.passed:
                outcome = "passed"
            elif report.when != "call":
                outcome = "error"
            else:
                outcome = "failed"
            message = "" if report.passed else _shorten(str(report.longrepr))
            self.tests.append(
                {
                    "name": report.nodeid,
                    "outcome": outcome,
                    "duration_seconds": round(report.duration, 4),
                    "message": message,
                }
            )


def _shorten(text: str, limit: int = 4000) -> str:
    """Trim a failure repr so a pathological traceback can't flood the payload."""
    return text if len(text) <= limit else text[:limit] + "\n... [truncated]"


def _stage_workdir() -> None:
    """Copy user files from the read-only mount into the writable tmpfs workdir."""
    _WORK_DIR.mkdir(parents=True, exist_ok=True)
    for src in _CODE_DIR.iterdir():
        if src.is_file():
            shutil.copy(src, _WORK_DIR / src.name)


def main() -> int:
    """Run the graded pytest session and emit the JSON result payload."""
    _stage_workdir()
    # Root FS is read-only (--read-only); /work tmpfs is the only writable place,
    # so pytest's output capture and any temp files must live there.
    os.environ["TMPDIR"] = str(_WORK_DIR)
    os.chdir(_WORK_DIR)

    collector = _Collector()
    # -p no:cacheprovider: nothing to persist; -q: keep captured output small.
    exit_code = pytest.main(
        ["-q", "-p", "no:cacheprovider", "--no-header", str(_WORK_DIR)],
        plugins=[collector],
    )

    passed = exit_code == 0 and len(collector.tests) > 0
    # 0 collected tests usually means a misnamed test file, not a real pass/fail —
    # surface it as a runner error so the user sees a clear cause, not silent failure.
    runner_error = "no tests collected (check the test filename)" if not collector.tests else ""
    payload = {
        "passed": passed,
        "exit_code": int(exit_code),
        "tests": collector.tests,
        "stdout": "",  # captured-output forwarding kept minimal for the MVP
        "runner_error": runner_error,
    }
    print(_RESULT_BEGIN)
    print(json.dumps(payload))
    print(_RESULT_END)
    return 0  # always 0: grading outcome travels in the JSON, not the exit code


if __name__ == "__main__":
    sys.exit(main())
