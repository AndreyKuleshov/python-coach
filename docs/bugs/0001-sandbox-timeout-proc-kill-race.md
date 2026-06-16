# Bug 0001 — SandboxClient timeout path can raise `ProcessLookupError`

**Severity:** medium (availability) — escapes a method contracted never to raise on user input.
**Component:** `services/api/src/python_coach/clients/sandbox.py` (`_docker_run`, timeout branch).
**Status:** FIXED (2026-06-12) — `proc.kill()` in the timeout branch is now wrapped in
`contextlib.suppress(ProcessLookupError)` in `_docker_run`, so `run()` can no longer raise on
a concurrent-timeout race. The two security regressions no longer carry `xfail` and pass outright.

## Symptom

When two (or more) infinite-loop submissions hit the wall-clock timeout at
nearly the same moment, `SandboxClient.run` intermittently raises:

```
File ".../clients/sandbox.py", line 120, in _docker_run
    proc.kill()
File ".../asyncio/base_subprocess.py", line 151, in _check_proc
    raise ProcessLookupError()
ProcessLookupError
```

This propagates out of `run()` (whose docstring promises "never raises on user
error"), out of the controller, and surfaces to the client as an unhandled
500 instead of a structured `status=timeout` verdict.

Standalone the timeout path is fine; the defect only manifests under concurrent
timeouts (reproduced with `pytest -n auto` / `-n 4`, ~1 in 3 runs).

## Cause

In the timeout branch the cleanup order is:

```python
except TimeoutError:
    await self._force_remove(container)   # docker rm -f <name>
    proc.kill()                           # <-- races here
    await proc.wait()
```

`docker run --rm` plus the explicit `docker rm -f` removes the container and the
host `docker run` CLI process exits and is reaped (by `--init`/the event loop)
**before** `proc.kill()` runs. asyncio's subprocess transport has already
cleared `_proc`, so `kill()` -> `_check_proc()` raises `ProcessLookupError`.
The window is widened by host load when several containers are torn down at once.

## Fix (product change — not made by QA)

Guard the kill against an already-reaped process, e.g.:

```python
except TimeoutError:
    await self._force_remove(container)
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    await proc.wait()
    return self._runner_error(...)
```

(`proc.wait()` after a force-removed/reaped process returns immediately.)

## Test impact

The security regressions in
`services/api/tests/test_sandbox_security_api.py` exercise this path:

- `test_infinite_loop_times_out_without_hanging`
- `test_timeout_leaves_no_leaked_container`

Both pass reliably standalone but can flake under concurrent execution because
of this race. They are marked `xfail(strict=False)` referencing this bug so the
suite stays honest under `-n auto` without masking the defect; once the
`proc.kill()` guard lands, drop the `xfail`.
