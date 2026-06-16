"""Docker-based sandbox client — runs user code + exercise tests in isolation.

THREAT MODEL (summary; full version in README/CONTEXT): user code is hostile.
We never import or exec it in the API process. Each submission runs in a
throwaway Docker container with: no network, read-only root FS, dropped
capabilities, a memory cap, a CPU cap, a PID cap, and a host-enforced
wall-clock timeout that kills the container. Files are written to a host temp
dir mounted read-only at /code; the in-container runner copies them to a
tmpfs workdir before running pytest, so nothing the user writes persists.

This client only orchestrates `docker run`; the grading logic lives in the
in-container runner (services/sandbox/runner/run_tests.py).
"""

import asyncio
import contextlib
import json
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog

from python_coach.clients.sandbox_result import TestOutcome, TestResult, TestRunResult
from python_coach.settings import Settings

log = structlog.get_logger(__name__)

# Marker the in-container runner prints around its JSON payload so we can
# extract it even if pytest emits stray output around it.
_RESULT_BEGIN = "<<<PYTHON_COACH_RESULT_BEGIN>>>"
_RESULT_END = "<<<PYTHON_COACH_RESULT_END>>>"

_MAX_CAPTURE = 20_000  # truncate stdout/stderr we surface to the UI


@dataclass(frozen=True, slots=True)
class SandboxFile:
    """One file to materialize inside the sandbox before running pytest."""

    name: str
    content: str


class SandboxClient:
    """Runs a graded pytest session for one submission inside a Docker container."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self, solution: SandboxFile, tests: list[SandboxFile]) -> TestRunResult:
        """Grade `solution` against `tests` in an isolated container; never raises on user error."""
        # Stage files in a host temp dir mounted read-only into the container.
        with tempfile.TemporaryDirectory(prefix="pcoach-") as tmp:
            code_dir = Path(tmp)
            (code_dir / solution.name).write_text(solution.content, encoding="utf-8")
            for test in tests:
                (code_dir / test.name).write_text(test.content, encoding="utf-8")

            return await self._docker_run(code_dir)

    async def _docker_run(self, code_dir: Path) -> TestRunResult:
        """Invoke `docker run` with hard isolation and parse the runner's JSON."""
        s = self._settings
        # Named container so a wall-clock timeout can force-remove the actual
        # container — killing the host `docker run` CLI alone leaves it running.
        container = f"pcoach-{uuid.uuid4().hex}"
        args = [
            s.docker_bin,
            "run",
            "--rm",
            "--name",
            container,
            "--init",  # PID 1 reaps zombies / forwards signals to children
            "--network",
            "none",  # no network access at all
            "--read-only",  # immutable root filesystem
            "--tmpfs",
            # ephemeral writable workdir owned by the unprivileged sandbox uid (10001)
            "/work:rw,size=32m,noexec,uid=10001,gid=10001",
            "--memory",
            s.sandbox_memory_limit,
            "--memory-swap",
            s.sandbox_memory_limit,  # disable swap escape hatch
            "--cpus",
            s.sandbox_cpu_limit,
            "--pids-limit",
            "128",  # cap fork bombs
            "--cap-drop",
            "ALL",  # drop all Linux capabilities
            "--security-opt",
            "no-new-privileges",
            "-v",
            f"{code_dir}:/code:ro",  # user files, read-only
            s.sandbox_image,
        ]

        # Host-side wall-clock kill: the timeout backstops cgroup CPU limits
        # against pure-Python infinite loops that never yield.
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return self._runner_error("docker binary not found on host")

        # `finally` force-removes the container on EVERY exit path (success,
        # failure, timeout, exception) so no container outlives this call.
        try:
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=s.sandbox_wall_timeout_seconds
                )
            except TimeoutError:
                # Killing the CLI process does NOT stop the container; remove it
                # by name so a `while True: pass` submission cannot survive.
                await self._force_remove(container)
                # The container teardown may already have reaped the host
                # `docker run` CLI process; kill() then raises ProcessLookupError.
                # run() must never raise on a timeout, so swallow that race.
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                await proc.wait()
                return self._runner_error(
                    f"execution exceeded {s.sandbox_wall_timeout_seconds}s wall-clock limit"
                )

            stdout = stdout_b.decode("utf-8", "replace")
            stderr = stderr_b.decode("utf-8", "replace")
            return self._parse(stdout, stderr, proc.returncode or 0)
        finally:
            # Backstop: --rm cleans up on normal exit, but a crash/exception
            # between spawn and reap could leak the container otherwise.
            await self._force_remove(container)

    async def _force_remove(self, container: str) -> None:
        """Force-remove the named container, ignoring the common 'already gone' case."""
        try:
            rm = await asyncio.create_subprocess_exec(
                self._settings.docker_bin,
                "rm",
                "-f",
                container,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await rm.wait()
        except OSError:
            log.warning("sandbox.force_remove_failed", container=container)

    def _parse(self, stdout: str, stderr: str, return_code: int) -> TestRunResult:
        """Extract the runner's JSON payload between markers and build a result."""
        begin = stdout.find(_RESULT_BEGIN)
        end = stdout.find(_RESULT_END)
        if begin == -1 or end == -1 or end < begin:
            log.warning("sandbox.no_result_marker", return_code=return_code)
            return self._runner_error(
                "runner produced no result payload (likely crashed or was killed)",
                stdout=stdout,
                stderr=stderr,
            )

        payload_raw = stdout[begin + len(_RESULT_BEGIN) : end].strip()
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            return self._runner_error("runner emitted invalid JSON", stdout=stdout, stderr=stderr)

        # The runner itself can flag an infrastructure-level problem (e.g. no
        # tests collected); honour it rather than reporting a silent failure.
        payload_error = payload.get("runner_error", "")
        if payload_error:
            return self._runner_error(
                payload_error, stdout=payload.get("stdout", ""), stderr=stderr
            )

        tests = [
            TestResult(
                name=t["name"],
                outcome=TestOutcome(t["outcome"]),
                duration_seconds=float(t.get("duration_seconds", 0.0)),
                message=t.get("message", ""),
            )
            for t in payload.get("tests", [])
        ]
        passed_count = sum(1 for t in tests if t.outcome == TestOutcome.PASSED)
        failed_count = len(tests) - passed_count
        return TestRunResult(
            passed=bool(payload.get("passed", False)),
            total=len(tests),
            passed_count=passed_count,
            failed_count=failed_count,
            tests=tests,
            stdout=payload.get("stdout", "")[:_MAX_CAPTURE],
            stderr=stderr[:_MAX_CAPTURE],
            runner_error="",
        )

    @staticmethod
    def _runner_error(message: str, stdout: str = "", stderr: str = "") -> TestRunResult:
        """Build a failed result representing a runner/infrastructure failure."""
        return TestRunResult(
            passed=False,
            total=0,
            passed_count=0,
            failed_count=0,
            tests=[],
            stdout=stdout[:_MAX_CAPTURE],
            stderr=stderr[:_MAX_CAPTURE],
            runner_error=message,
        )
