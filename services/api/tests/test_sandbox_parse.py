"""Unit tests for SandboxClient parsing + timeout handling (no Docker needed)."""

import asyncio
import json
from typing import Any

import pytest

from python_coach.clients.sandbox import (
    _RESULT_BEGIN,
    _RESULT_END,
    SandboxClient,
    SandboxFile,
)
from python_coach.clients.sandbox_result import TestOutcome
from python_coach.settings import Settings


def _client(wall_timeout_seconds: int = 10) -> SandboxClient:
    """Build a SandboxClient over throwaway settings (no real Docker is invoked)."""
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost:5544/db",
        sandbox_image="pcoach-sandbox:test",
        sandbox_wall_timeout_seconds=wall_timeout_seconds,
        sandbox_memory_limit="256m",
        sandbox_cpu_limit="1.0",
        docker_bin="docker",
        jwt_secret="test-secret",
        jwt_access_token_minutes=60,
        jwt_confirm_token_minutes=60,
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        smtp_from="no-reply@example.com",
        public_base_url="http://test",
    )
    return SandboxClient(settings)


def _wrap(payload: dict[str, Any]) -> str:
    """Wrap a runner payload in the begin/end markers as the container would."""
    return f"prefix noise\n{_RESULT_BEGIN}\n{json.dumps(payload)}\n{_RESULT_END}\ntrailing"


def test_parse_missing_marker_is_runner_error() -> None:
    res = _client()._parse("no markers here", "boom", return_code=137)
    assert res.runner_error
    assert res.passed is False
    assert res.total == 0


def test_parse_invalid_json_is_runner_error() -> None:
    bad = f"{_RESULT_BEGIN}\nnot-json{{\n{_RESULT_END}"
    res = _client()._parse(bad, "", return_code=0)
    assert "invalid JSON" in res.runner_error


def test_parse_runner_error_in_payload_is_surfaced() -> None:
    payload = {"passed": False, "tests": [], "runner_error": "no tests collected"}
    res = _client()._parse(_wrap(payload), "", return_code=0)
    assert res.runner_error == "no tests collected"


def test_parse_valid_payload_counts_outcomes() -> None:
    payload = {
        "passed": False,
        "tests": [
            {"name": "t::a", "outcome": "passed", "duration_seconds": 0.1},
            {"name": "t::b", "outcome": "failed", "duration_seconds": 0.2, "message": "boom"},
            {"name": "t::c", "outcome": "error", "duration_seconds": 0.0},
        ],
    }
    res = _client()._parse(_wrap(payload), "stderr text", return_code=1)
    assert res.runner_error == ""
    assert res.total == 3
    assert res.passed_count == 1
    assert res.failed_count == 2
    assert res.tests[1].outcome == TestOutcome.FAILED
    assert res.tests[1].message == "boom"


class _HangingProcess:
    """Fake asyncio subprocess whose communicate() never returns, to force a timeout."""

    returncode: int | None = None

    async def communicate(self) -> tuple[bytes, bytes]:
        await asyncio.Event().wait()  # blocks forever
        raise AssertionError("unreachable")

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


async def test_timeout_path_produces_timeout_runner_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(wall_timeout_seconds=0)

    removed: list[str] = []

    async def _fake_create(*args: Any, **kwargs: Any) -> Any:
        # The `docker rm -f` cleanup call records the container name then succeeds.
        if "rm" in args:
            removed.append(args[-1])

            class _Done:
                async def wait(self) -> int:
                    return 0

            return _Done()
        return _HangingProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create)

    res = await client.run(SandboxFile(name="solution.py", content="while True: pass"), tests=[])

    assert res.runner_error
    assert "wall-clock" in res.runner_error
    # Cleanup must run on the timeout path so no container is leaked.
    assert removed, "expected docker rm -f to be invoked on timeout"
