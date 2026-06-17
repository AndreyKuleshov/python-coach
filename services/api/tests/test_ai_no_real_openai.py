"""Safety net: the in-process app must NEVER reach the real OpenAI API in tests.

Same lesson as the email-spam bug: a real network call from the suite costs
money and is flaky. Two guards here:

1. The ``get_llm_client`` dependency is overridden with the fake for the whole
   session (installed in ``conftest.session_maker``) — assert that override is
   in place, so a future refactor that drops it fails loudly.
2. If anything ever does build the real ``AsyncOpenAI`` client and call it, we
   trip an explicit failure by monkeypatching its request path to raise.
"""

import httpx
import pytest

from conftest import _FakeLLMClient
from python_coach.app import app
from python_coach.clients.llm import LLMClient
from python_coach.transport.deps import get_llm_client

pytestmark = [pytest.mark.db]


@pytest.mark.security
async def test_llm_dependency_is_overridden_with_fake(
    client: httpx.AsyncClient,
) -> None:
    """The session installs the fake LLM override — no real OpenAI client is used.

    ``client`` depends (transitively) on ``session_maker``, which registers the
    override; resolving the override here proves it is active for in-process tests.
    """
    override = app.dependency_overrides.get(get_llm_client)
    assert override is not None, "LLM dependency override missing — tests could hit real OpenAI"
    produced = override()
    assert isinstance(produced, _FakeLLMClient)
    assert not isinstance(produced, LLMClient)


@pytest.mark.security
async def test_hint_does_not_perform_network_call(
    auth_client: httpx.AsyncClient,
    seed_exercise: "object",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even if a real LLMClient leaked in, its network path is tripwired to fail.

    We patch the real client's completion method to explode; the hint call must
    still succeed (200) because it goes through the fake, proving the real path
    is never taken.
    """

    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("real OpenAI completion was called from a test")

    monkeypatch.setattr(LLMClient, "_complete", _boom)
    se = seed_exercise  # typed as object to avoid importing the dataclass twice
    res = await auth_client.post(
        f"/api/exercises/{se.exercise_id}/hint",  # type: ignore[attr-defined]
        json={"locale": "en"},
    )
    assert res.status_code == 200, res.text
