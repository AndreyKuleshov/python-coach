"""Application settings — read env once at startup, validate, freeze.

Per .claude/rules/all-languages.md every field is required (no in-code
defaults that mask environment drift), with the sole pragmatic exception of
bind host/port which are operational knobs, not environment secrets.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Frozen process-wide configuration sourced exclusively from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    # === Database ===
    # Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host:5432/db
    database_url: str

    # === Sandbox (code-execution isolation) ===
    # Docker image tag built from services/sandbox/Dockerfile.
    sandbox_image: str
    # Hard wall-clock limit (seconds) for one submission run, enforced by the host.
    sandbox_wall_timeout_seconds: int
    # Memory cap passed to `docker run --memory`, e.g. "256m".
    sandbox_memory_limit: str
    # CPU cap passed to `docker run --cpus`, e.g. "1.0".
    sandbox_cpu_limit: str
    # Path to the docker CLI on the host running the API.
    docker_bin: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (read once, cached)."""
    return Settings()  # type: ignore[call-arg]
