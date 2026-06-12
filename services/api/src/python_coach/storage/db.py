"""Async engine + session factory wiring.

The engine is created once from settings and reused; sessions are per-request
(see deps.py). asyncpg is the driver per the fixed stack.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from python_coach.settings import get_settings


def make_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine from validated settings."""
    settings = get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the lazily-built, process-wide session factory."""
    global _engine, _session_factory
    if _session_factory is None:
        _engine = make_engine()
        _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield one session per request and ensure it is closed afterwards."""
    async with session_factory()() as session:
        yield session
