"""FastAPI dependency stitching — the single place layers are wired together.

Builds Storage(session), the SandboxClient, the EmailClient, the AuthConfig, and
resolves the current user from the bearer token for protected routes.
"""

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from python_coach.clients.email import EmailClient
from python_coach.clients.llm import LLMClient
from python_coach.clients.sandbox import SandboxClient
from python_coach.controllers.auth import AuthConfig
from python_coach.controllers.security import InvalidTokenError, read_access_token
from python_coach.settings import Settings, get_settings
from python_coach.storage.db import get_session
from python_coach.storage.models.user import User
from python_coach.storage.storage import Storage


def get_storage(session: Annotated[AsyncSession, Depends(get_session)]) -> Storage:
    """Build the request-scoped Storage facade over the request session."""
    return Storage(session)


def get_sandbox(settings: Annotated[Settings, Depends(get_settings)]) -> SandboxClient:
    """Build the sandbox client from settings."""
    return SandboxClient(settings)


def get_email_client(settings: Annotated[Settings, Depends(get_settings)]) -> EmailClient:
    """Build the email client (SMTP or log-fallback) from settings."""
    return EmailClient(settings)


def get_llm_client(settings: Annotated[Settings, Depends(get_settings)]) -> LLMClient:
    """Build the OpenAI-backed LLM client (overridable in tests via this dep)."""
    return LLMClient(settings)


def get_auth_config(settings: Annotated[Settings, Depends(get_settings)]) -> AuthConfig:
    """Bundle the JWT/email-confirmation knobs from settings for the auth use-cases."""
    return AuthConfig(
        secret=settings.jwt_secret,
        access_token_minutes=settings.jwt_access_token_minutes,
        confirm_token_minutes=settings.jwt_confirm_token_minutes,
        public_base_url=settings.public_base_url,
    )


StorageDep = Annotated[Storage, Depends(get_storage)]
SandboxDep = Annotated[SandboxClient, Depends(get_sandbox)]
EmailClientDep = Annotated[EmailClient, Depends(get_email_client)]
LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]
AuthConfigDep = Annotated[AuthConfig, Depends(get_auth_config)]

# auto_error=False so a missing header yields our own 401 (not a 403) and the
# message is uniform with a bad/expired token.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    storage: StorageDep,
    config: AuthConfigDep,
) -> User:
    """Resolve the bearer token to the current user; 401 on any failure."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        user_id = read_access_token(credentials.credentials, config.secret)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc

    user = await storage.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="account no longer exists")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
