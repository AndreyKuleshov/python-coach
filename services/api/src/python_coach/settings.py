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

    # === Auth (JWT) ===
    # HS256 signing secret for access + email-confirmation tokens. Required, no default.
    jwt_secret: str
    # Access token lifetime in minutes.
    jwt_access_token_minutes: int
    # Email-confirmation token lifetime in minutes.
    jwt_confirm_token_minutes: int

    # === Email (SMTP, optional) ===
    # When smtp_host is empty the confirmation link is logged (structlog) instead
    # of sent — usable/testable locally without SMTP creds.
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    # Public base URL the confirmation link points at (e.g. http://localhost:8077).
    public_base_url: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (read once, cached)."""
    return Settings()  # type: ignore[call-arg]
