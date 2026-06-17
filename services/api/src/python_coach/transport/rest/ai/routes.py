"""AI endpoints: exercise hints + lesson-excerpt chat, and their DTOs.

Both endpoints REQUIRE a valid bearer token (CurrentUserDep): the AI features
are auth-gated like the rest of the content. When no OpenAI key is configured
the AI use-cases raise AIDisabledError, mapped here to 503 so the frontend can
hide the hint buttons + chat widget rather than the app crashing.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from python_coach.controllers.ai import (
    AIDisabledError,
    explain_excerpt,
    generate_hint,
)
from python_coach.controllers.lessons import LessonLockedError
from python_coach.controllers.submissions import ExerciseNotFoundError
from python_coach.transport.deps import CurrentUserDep, LLMClientDep, StorageDep

router = APIRouter(prefix="/api", tags=["ai"])

# The two UI locales; anything else falls back to English in the client.
_SUPPORTED_LOCALES = {"en", "ru"}


def _normalize_locale(locale: str) -> str:
    """Clamp an incoming locale to a supported one (default English)."""
    return locale if locale in _SUPPORTED_LOCALES else "en"


class HintRequest(BaseModel):
    """Body for an exercise-hint request — only the UI locale is needed."""

    locale: str = "en"


class HintResponse(BaseModel):
    """The generated approach hint (never the full solution)."""

    hint: str


class ChatRequest(BaseModel):
    """Body for the lesson-explanation chat — a pasted excerpt + optional question."""

    # Caps mirror the client-side limits; defence in depth against token-bill blowups.
    excerpt: str = Field(min_length=1, max_length=6000)
    question: str = Field(default="", max_length=1000)
    locale: str = "en"


class ChatResponse(BaseModel):
    """The assistant's explanation of the pasted excerpt."""

    answer: str


@router.post("/exercises/{exercise_id}/hint", response_model=HintResponse)
async def exercise_hint(
    exercise_id: int,
    body: HintRequest,
    user: CurrentUserDep,
    storage: StorageDep,
    llm: LLMClientDep,
) -> HintResponse:
    """Return an OpenAI-generated approach hint for an exercise the user can see."""
    try:
        hint = await generate_hint(
            user.id or 0, exercise_id, _normalize_locale(body.locale), storage, llm
        )
    except AIDisabledError as exc:
        raise HTTPException(status_code=503, detail="AI features are not configured") from exc
    except ExerciseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="exercise not found") from exc
    except LessonLockedError as exc:
        raise HTTPException(status_code=403, detail="lesson is locked") from exc
    return HintResponse(hint=hint)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: CurrentUserDep,
    llm: LLMClientDep,
) -> ChatResponse:
    """Explain a pasted lesson excerpt in more detail, in the requested locale."""
    try:
        answer = await explain_excerpt(
            body.excerpt, body.question, _normalize_locale(body.locale), llm
        )
    except AIDisabledError as exc:
        raise HTTPException(status_code=503, detail="AI features are not configured") from exc
    return ChatResponse(answer=answer)
