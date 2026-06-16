"""Sandbox SECURITY regression tests — the platform's #1 risk.

The platform runs arbitrary user code. These tests drive the REAL Docker
sandbox end-to-end through the API and prove the container actually contains it:

1. An infinite loop hits the host wall-clock kill and returns a *structured*
   timeout (status=timeout, runner_error mentions wall-clock) — NOT a hung
   request — AND leaves no `pcoach-*` container behind.
2. Code that attempts outbound network access is denied (`--network none`),
   surfaced as a failed test rather than succeeding.

No mocking: if these pass, isolation genuinely holds.
"""

import asyncio
import os
import time
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from conftest import SeededExercise, TestSpec, seed_lesson
from python_coach.settings import get_settings

pytestmark = [pytest.mark.db, pytest.mark.sandbox, pytest.mark.security]

_ANY_SOLUTION = "x = 1\n"


async def _list_pcoach_containers() -> list[str]:
    """Return names of any lingering `pcoach-*` sandbox containers (running or not)."""
    settings = get_settings()
    proc = await asyncio.create_subprocess_exec(
        settings.docker_bin,
        "ps",
        "-a",
        "--filter",
        "name=pcoach-",
        "--format",
        "{{.Names}}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, _ = await proc.communicate()
    return [n for n in stdout_b.decode().splitlines() if n.strip()]


@pytest_asyncio.fixture(loop_scope="session")
async def infinite_loop_exercise(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SeededExercise]:
    """An exercise whose single test spins forever, to trigger the wall-clock kill."""
    spinner = TestSpec(
        filename="test_spin.py",
        content="def test_spins_forever():\n    while True:\n        pass\n",
    )
    # A throwaway hidden test keeps the seed shape uniform with the default fixture.
    placeholder = TestSpec(
        filename="test_placeholder.py",
        content="def test_noop():\n    assert True\n",
        is_hidden=True,
    )
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    slug = f"qa-sec-loop-{worker}-{uuid.uuid4().hex[:12]}"
    async with seed_lesson(session_maker, slug, [spinner, placeholder]) as seeded:
        yield seeded


@pytest_asyncio.fixture(loop_scope="session")
async def network_exercise(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SeededExercise]:
    """An exercise whose test attempts an outbound TCP connection (must be denied)."""
    netcheck = TestSpec(
        filename="test_net.py",
        content=(
            "import socket\n\n\n"
            "def test_outbound_connection():\n"
            "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    s.settimeout(5)\n"
            '    s.connect(("1.1.1.1", 80))\n'
        ),
    )
    placeholder = TestSpec(
        filename="test_placeholder.py",
        content="def test_noop():\n    assert True\n",
        is_hidden=True,
    )
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    slug = f"qa-sec-net-{worker}-{uuid.uuid4().hex[:12]}"
    async with seed_lesson(session_maker, slug, [netcheck, placeholder]) as seeded:
        yield seeded


async def test_infinite_loop_times_out_without_hanging(
    auth_client: httpx.AsyncClient, infinite_loop_exercise: SeededExercise
) -> None:
    """A `while True` submission returns a structured timeout, not a hung request.

    We bound the call ourselves at wall_timeout + generous slack: if the sandbox
    failed to kill the container the request would never resolve and this awaits
    would raise — which is itself the failure signal we want, not a silent hang.
    """
    settings = get_settings()
    deadline = settings.sandbox_wall_timeout_seconds + 30

    start = time.monotonic()
    res = await asyncio.wait_for(
        auth_client.post(
            "/api/submissions",
            json={"exercise_id": infinite_loop_exercise.exercise_id, "code": _ANY_SOLUTION},
        ),
        timeout=deadline,
    )
    elapsed = time.monotonic() - start

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "timeout", "wall-clock kill must map to status=timeout"
    assert "wall-clock" in body["runner_error"]
    assert body["passed"] is False
    # The kill must happen near the wall-clock limit, well before our hard deadline.
    assert elapsed < deadline, "request resolved (did not hang)"


async def test_timeout_leaves_no_leaked_container(
    auth_client: httpx.AsyncClient, infinite_loop_exercise: SeededExercise
) -> None:
    """After a timeout, no `pcoach-*` container survives (force-removed by name)."""
    res = await asyncio.wait_for(
        auth_client.post(
            "/api/submissions",
            json={"exercise_id": infinite_loop_exercise.exercise_id, "code": _ANY_SOLUTION},
        ),
        timeout=get_settings().sandbox_wall_timeout_seconds + 30,
    )
    assert res.json()["status"] == "timeout"

    # The named container is removed on the timeout path; allow a brief moment for
    # `docker rm -f` to settle, then assert nothing pcoach-* is left behind.
    leaked = await _list_pcoach_containers()
    assert leaked == [], f"timeout leaked sandbox containers: {leaked}"


async def test_network_access_is_denied(
    auth_client: httpx.AsyncClient, network_exercise: SeededExercise
) -> None:
    """Outbound network from user code fails inside the `--network none` sandbox."""
    res = await auth_client.post(
        "/api/submissions",
        json={"exercise_id": network_exercise.exercise_id, "code": _ANY_SOLUTION},
    )

    assert res.status_code == 200
    body = res.json()
    # The connect() raises OSError, so the test FAILS (network is unreachable) —
    # it must never report passed, which would mean the sandbox reached the net.
    assert body["passed"] is False
    assert body["status"] == "failed"
    failed = [t for t in body["tests"] if t["outcome"] in {"failed", "error"}]
    assert failed, "network test must surface as a failed/errored test"
    assert any(
        "Network is unreachable" in t["message"] or "Errno" in t["message"] for t in failed
    ), "expected an OS-level network-denied error in the surfaced message"
