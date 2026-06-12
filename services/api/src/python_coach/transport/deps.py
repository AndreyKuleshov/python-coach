"""FastAPI dependency stitching — the single place layers are wired together.

Builds Storage(session) and the SandboxClient. (No current-user resolution
yet: single-user MVP.)
"""

from typing import Annotated

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from python_coach.clients.sandbox import SandboxClient
from python_coach.settings import Settings, get_settings
from python_coach.storage.db import get_session
from python_coach.storage.storage import Storage


def get_storage(session: Annotated[AsyncSession, Depends(get_session)]) -> Storage:
    """Build the request-scoped Storage facade over the request session."""
    return Storage(session)


def get_sandbox(settings: Annotated[Settings, Depends(get_settings)]) -> SandboxClient:
    """Build the sandbox client from settings."""
    return SandboxClient(settings)


StorageDep = Annotated[Storage, Depends(get_storage)]
SandboxDep = Annotated[SandboxClient, Depends(get_sandbox)]
