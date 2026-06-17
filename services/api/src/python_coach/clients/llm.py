"""LLM client — wraps OpenAI for exercise hints and lesson-excerpt explanations.

External upstream (the OpenAI API), so it lives in `clients/` per api-layers.
Uses the ASYNC client (`AsyncOpenAI`) so a chat completion never blocks the
event loop. Prompts are kept server-side here; the routes only pass user inputs.

Two graceful escape hatches, both mirroring the EmailClient/SMTP pattern:

- When `openai_api_key` is empty the AI features are DISABLED. `is_enabled` is
  False and the controllers turn that into a 503 — the app never crashes on a
  missing key.
- When `openai_fake` is set the client returns deterministic canned text WITHOUT
  any network call. Tests (and the UI live-server) use this so the suite never
  spends real tokens or depends on OpenAI being reachable.

One class, no Protocol/ABC — there is a single implementation.
"""

import structlog
from openai import AsyncOpenAI

from python_coach.settings import Settings

log = structlog.get_logger(__name__)

# Hard caps on what we forward to the model — a runaway excerpt/question would
# blow up the token bill. Truncation is silent; the model still gets enough
# context to answer for a learning excerpt.
_MAX_EXCERPT_CHARS = 6000
_MAX_QUESTION_CHARS = 1000
_MAX_STATEMENT_CHARS = 4000
_MAX_STARTER_CHARS = 2000

# Keep replies short and cheap; these are hints/explanations, not essays.
_HINT_MAX_TOKENS = 320
_CHAT_MAX_TOKENS = 600

_LOCALE_NAMES = {"en": "English", "ru": "Russian"}


def _locale_name(locale: str) -> str:
    """Map a UI locale code to a language name the model understands."""
    return _LOCALE_NAMES.get(locale, "English")


class LLMClient:
    """Generates hints and lesson explanations via OpenAI (async), or canned text."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.openai_model
        self._fake = settings.openai_fake
        self._api_key = settings.openai_api_key
        # Only build a real client when we have a key and are not in fake mode;
        # otherwise the feature is disabled and we never touch the network.
        self._client = (
            AsyncOpenAI(api_key=settings.openai_api_key)
            if settings.openai_api_key and not settings.openai_fake
            else None
        )

    @property
    def is_enabled(self) -> bool:
        """True when AI features should be offered (key present, fake or real)."""
        return bool(self._api_key) or self._fake

    async def hint(self, statement: str, starter_code: str, locale: str) -> str:
        """An approach hint for an exercise — never the full solution.

        The hidden reference solution is deliberately NOT passed in by the
        caller; we only ever see the public statement + starter code, so the
        model cannot leak it.
        """
        if self._fake:
            return _fake_hint(locale)

        if len(statement) > _MAX_STATEMENT_CHARS:
            log.warning(
                "hint: statement truncated", original=len(statement), cap=_MAX_STATEMENT_CHARS
            )
        if len(starter_code) > _MAX_STARTER_CHARS:
            log.warning(
                "hint: starter_code truncated", original=len(starter_code), cap=_MAX_STARTER_CHARS
            )
        statement = statement[:_MAX_STATEMENT_CHARS]
        starter_code = starter_code[:_MAX_STARTER_CHARS]
        system = (
            "You are a Python tutor for a test-automation learner. Give ONE short "
            "hint about the APPROACH to the exercise below — a nudge in the right "
            "direction (which concept, function, or pattern to reach for). "
            "Do NOT write the full solution or working code that solves it; at "
            f"most a tiny illustrative snippet. Answer in {_locale_name(locale)}, "
            "in 2-4 sentences."
        )
        user = f"Exercise statement:\n{statement}\n\nStarter code:\n{starter_code}"
        return await self._complete(system, user, _HINT_MAX_TOKENS)

    async def explain(self, excerpt: str, question: str, locale: str) -> str:
        """Explain a pasted lesson excerpt in more detail, scoped to that excerpt."""
        if self._fake:
            return _fake_explanation(locale)

        if len(excerpt) > _MAX_EXCERPT_CHARS:
            log.warning("explain: excerpt truncated", original=len(excerpt), cap=_MAX_EXCERPT_CHARS)
        if len(question) > _MAX_QUESTION_CHARS:
            log.warning(
                "explain: question truncated", original=len(question), cap=_MAX_QUESTION_CHARS
            )
        excerpt = excerpt[:_MAX_EXCERPT_CHARS]
        question = question[:_MAX_QUESTION_CHARS]
        system = (
            "You are a Python learning assistant embedded in a lesson page. Your "
            "ONLY job is to explain, in more detail, the lesson excerpt the user "
            "pastes — clarify concepts, give small examples, answer questions "
            "about it. If the request is unrelated to learning Python from the "
            "given excerpt, politely decline and steer back to the lesson "
            f"material. Answer in {_locale_name(locale)}."
        )
        question_part = f"\n\nMy question: {question}" if question else ""
        user = f"Lesson excerpt:\n{excerpt}{question_part}"
        return await self._complete(system, user, _CHAT_MAX_TOKENS)

    async def _complete(self, system: str, user: str, max_tokens: int) -> str:
        """Run one chat completion and return the trimmed text content."""
        # Guard: _complete is only reached for the real path; fake/disabled are
        # handled by the callers / is_enabled before we get here.
        if self._client is None:
            raise RuntimeError("LLM client invoked without an API key")

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.4,
        )
        content = response.choices[0].message.content or ""
        return content.strip()


def _fake_hint(locale: str) -> str:
    """Deterministic offline hint used in fake mode (tests / UI live-server)."""
    if locale == "ru":
        return "Подсказка (офлайн-режим): подумайте, какое значение должна вернуть функция."
    return "Hint (offline mode): think about what value the function should return."


def _fake_explanation(locale: str) -> str:
    """Deterministic offline explanation used in fake mode (tests / UI live-server)."""
    if locale == "ru":
        return "Объяснение (офлайн-режим): этот фрагмент урока показывает базовую идею на примере."
    return "Explanation (offline mode): this lesson excerpt shows the core idea with an example."
